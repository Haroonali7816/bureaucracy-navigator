# The first call to LLM in the agentic pipeline.
# We feed a letter's image to Gemini and get back a JSON.
# That JSON is forced into our ExtractionResult schema.

import os

from google import genai
from google.genai import types
from pydantic import ValidationError

from app.schemas import ExtractionResult

MODEL_NAME = "gemini-3.6-flash"

_client: genai.Client | None = None

def _get_client() -> genai.Client:

    global _client
    if _client is None:
        api_key = os.environ["GEMINI_API_KEY"]
        _client = genai.Client(api_key=api_key)
    return _client

EXTRACTION_PROMPT = """You are reading a scanned letter sent to an international student or \
worker living in Germany, from a German authority (Ausländerbehörde, Finanzamt, \
Krankenkasse, university, Bürgeramt, or similar).

Read the letter image carefully and extract the following:

- authority: which of these sent the letter -- Ausländerbehörde, Finanzamt, Krankenkasse, \
University, Bürgeramt, or Other
- letter_type: one of -- appointment_notice, fee_tax_notice, document_request, \
deadline_warning, informational
- deadlines: every date the recipient must act by, each with a plain description of what is \
due on that date. If the letter has no real deadline (purely informational), return an empty \
list.
- required_actions: concrete things the recipient must do (e.g. "attend the appointment", \
"submit form X"). Empty list if none.
- required_documents: documents or proofs the recipient must provide or bring. Empty list if \
none.
- consequences: what happens if the recipient misses the deadline or ignores the letter, in \
one or two sentences. Null if the letter doesn't state any.
- contact_info: how to reach the sender (phone, address, reference number), if given. Null if \
none.
- confidence_flags: short notes about anything in the letter you found ambiguous, hard to \
read, or aren't fully sure about. Empty list if nothing was ambiguous.

Only report what the letter actually states. Do not guess a deadline that isn't written down."""

def classify_and_extract(image_path: str) -> ExtractionResult:

    client = _get_client()

    with open(image_path, "rb") as f:
        image_bytes = f.read()
    image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/png")

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[image_part, EXTRACTION_PROMPT],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=ExtractionResult,
            http_options=types.HttpOptions(timeout=120000),
        ),
    )

    try:
        return ExtractionResult.model_validate_json(response.text)
    except ValidationError as first_error:
        retry_prompt = (
           EXTRACTION_PROMPT
            + "\n\nYour previous answer did not match the required format. "
            + f"Validation error: {first_error}\n\nReturn corrected JSON only."
        )
        retry_response = client.models.generate_content(
           model=MODEL_NAME,
           contents=[image_part, retry_prompt],
           config=types.GenerateContentConfig(
               response_mime_type="application/json",
               response_schema=ExtractionResult,
                http_options=types.HttpOptions(timeout=120000),
           ),
        )

        return ExtractionResult.model_validate_json(retry_response.text)