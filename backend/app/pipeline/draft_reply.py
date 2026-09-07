import json
import os

from google import genai
from google.genai import types
from pydantic import ValidationError

from app.models import Extraction
from app.schemas import DraftReply

MODEL_NAME = "gemini-3.6-flash"

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ["GEMINI_API_KEY"]
        _client = genai.Client(api_key=api_key)
    return _client


DRAFT_REPLY_PROMPT_TEMPLATE = """You are drafting a reply, on behalf of an international \
student/worker living in Germany, to a letter they received from a German authority.

Below is what was already extracted and human-verified from the letter:
{extraction_json}

Write a draft reply appropriate for this letter_type:
- appointment_notice: confirm attendance (or request to reschedule if the letter allows it), \
referencing any reference/case number in contact_info.
- fee_tax_notice: acknowledge receipt and state the intended action (e.g. that payment will be \
made by the deadline, or request clarification if consequences suggest something is unclear). \
Do not invent a promise to pay if required_actions doesn't call for payment.
- document_request: confirm which requested documents will be provided and by when, \
referencing required_documents specifically.
- deadline_warning: acknowledge the warning and state the concrete action being taken to meet \
the deadline.
- informational: this letter requires no reply. Write only a short acknowledgment \
("noted, no action needed") rather than a formal reply -- do not invent an action to respond to.

Requirements:
- subject: a short subject line, in German.
- body_de: the full reply text, in formal German (Sie-form), addressed generically (no \
invented sender name -- leave a placeholder like [Ihr Name] for the user to fill in), \
referencing the authority ({authority}) and any reference number from contact_info if present.
- summary_en: 2-3 plain-English sentences explaining what body_de actually says, so someone \
who doesn't read German fluently can verify it before sending.

Only use information present in the extraction JSON above. Do not fabricate names, dates, or \
reference numbers that aren't there."""


def _extraction_summary(extraction: Extraction) -> str:
    return json.dumps(
        {
            "authority": extraction.authority,
            "letter_type": extraction.letter_type,
            "deadlines": extraction.deadlines,
            "required_actions": extraction.required_actions,
            "required_documents": extraction.required_documents,
            "consequences": extraction.consequences,
            "contact_info": extraction.contact_info,
        },
        indent=2,
        ensure_ascii=False,
    )


def generate_draft_reply(extraction: Extraction) -> DraftReply:
    client = _get_client()

    prompt = DRAFT_REPLY_PROMPT_TEMPLATE.format(
        extraction_json=_extraction_summary(extraction),
        authority=extraction.authority,
    )

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=DraftReply,
            http_options=types.HttpOptions(timeout=120000),
        ),
    )

    try:
        return DraftReply.model_validate_json(response.text)
    except ValidationError as first_error:
        retry_prompt = (
            prompt
            + "n\n\Your previous answer did not match the required format. "
            + f"Validation error: {first_error}\n\nReturn corrected JSON only."
        )
        retry_response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[retry_prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DraftReply,
                http_options=types.HttpOptions(timeout=120000),
            ),
        )
        return DraftReply.model_validate_json(retry_response.text)
