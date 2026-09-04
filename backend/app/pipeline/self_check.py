import os

from google import genai
from google.genai import types
from pydantic import ValidationError

from app.schemas import ExtractionResult, SelfCheckResult

MODEL_NAME = "gemini-3.6-flash"

_client: genai.Client | None = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ["GEMINI_API_KEY"]
        _client = genai.Client(api_key=api_key)
    return _client

SELF_CHECK_PROMPT_TEMPLATE = """You are auditing an automated extraction, not performing a \
fresh extraction yourself.

Below is a JSON object that another process extracted from the attached letter image. Your \
job is to check each field against what the letter image actually says -- not to re-read the \
letter and produce your own independent version of the answer.

Extracted JSON:
{extraction_json}

For each of these seven fields, rate your confidence that the extracted value is actually \
supported by the letter image: authority, letter_type, deadlines, required_actions, \
required_documents, consequences, contact_info.

Use these three levels:
- high: the field is directly and unambiguously stated in the letter.
- medium: the field is a reasonable inference from the letter, but not stated word-for-word \
(e.g. the letter type is implied by its structure and content rather than named outright).
- low: the field is not clearly supported by the letter, looks like a guess, or contradicts \
what the letter says.

For contact_info specifically: high means a phone number, address, or reference number is \
printed on the letter and matches exactly; medium means something contact-related is present \
but incomplete or has to be pieced together; low means the extracted value doesn't appear on \
the letter at all, or the letter gives no contact info and the field should have been null.

One known failure pattern to watch for specifically: this extractor has previously defaulted \
letter_type to fee_tax_notice for Finanzamt letters even when the letter doesn't actually \
state a fee or tax amount due. If the authority is Finanzamt, look specifically for an actual \
stated fee/tax figure or payment demand before rating letter_type high -- a Finanzamt letter \
that is really an appointment notice or purely informational should not be rated high \
confidence as fee_tax_notice just because of who sent it.

Set needs_human_review to true if ANY field is rated medium or low, or if you notice anything \
in the letter that contradicts the extracted JSON even in a field not listed above.

In reasoning, give one short sentence per field you rated medium or low, explaining \
specifically what in the letter doesn't support it. Empty list if everything is high \
confidence."""

def self_check(image_path:str, extraction: ExtractionResult)-> SelfCheckResult:
    client = _get_client()

    with open(image_path, "rb") as f:
        image_bytes = f.read()
    image_part = types.Part.from_bytes(data=image_bytes,mime_type="image/png")

    prompt = SELF_CHECK_PROMPT_TEMPLATE.format(
        extraction_json=extraction.model_dump_json(indent=2)
    )
    response = client.models.generate_content(
        model = MODEL_NAME,
        contents=[image_part, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SelfCheckResult,
            http_options=types.HttpOptions(timeout=120000),
        )
    )

    try:
        return SelfCheckResult.model_validate_json(response.text)
    except ValidationError as first_error:
        retry_prompt = (
            prompt
            + "\n\n Your previous answer did not match the required format."
            + f"Validation error: {first_error}\n\nReturn corrected JSON only"

        )
        retry_response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[image_part, retry_prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SelfCheckResult,
                http_options=types.HttpOptions(timeout=120000),
            ),
        )
        return SelfCheckResult.model_validate_json(retry_response.text)