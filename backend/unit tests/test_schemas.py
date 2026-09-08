# Schema validation tests.


from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas import (
    Deadline,
    ExtractionResult,
    SelfCheckResult,
    ExtractionEditRequest,
)


def test_extraction_result_accepts_a_minimal_valid_letter():
    result = ExtractionResult(authority="Finanzamt", letter_type="fee_tax_notice")
    
    assert result.deadlines == []
    assert result.required_actions == []
    assert result.required_documents == []
    assert result.confidence_flags == []
    assert result.consequences is None
    assert result.contact_info is None


def test_extraction_result_rejects_an_unknown_authority():
    with pytest.raises(ValidationError):
        ExtractionResult(authority="Some Random Landlord", letter_type="fee_tax_notice")


def test_extraction_result_rejects_an_unknown_letter_type():
    with pytest.raises(ValidationError):
        ExtractionResult(authority="Finanzamt", letter_type="threatening_letter")


def test_extraction_result_requires_authority_and_letter_type():
    with pytest.raises(ValidationError):
        ExtractionResult()  # neither field has a default --> both are mandatory


def test_deadline_rejects_an_invalid_date_string():
    with pytest.raises(ValidationError):
        Deadline(date="not-a-real-date", description="whatever this is for")


def test_deadline_accepts_a_real_date():
    d = Deadline(date="2026-09-15", description="Appointment for residence permit renewal")
    assert d.date == date(2026, 9, 15)


def test_extraction_result_validates_each_deadline_it_contains():
    # deadlines isn't just "a list" -- Pydantic validates every entry inside it too
    with pytest.raises(ValidationError):
        ExtractionResult(
            authority="Finanzamt",
            letter_type="fee_tax_notice",
            deadlines=[{"date": "not-a-real-date", "description": "..."}],
        )


def test_self_check_result_requires_all_seven_confidence_fields():
    # leaving one out (contact_info_confidence, here) must fail loudly, not silently pass
    with pytest.raises(ValidationError):
        SelfCheckResult(
            authority_confidence="high",
            letter_type_confidence="high",
            deadline_confidence="high",
            required_actions_confidence="high",
            required_documents_confidence="high",
            consequences_confidence="high",
            needs_human_review=False,
        )


def test_self_check_result_reasoning_defaults_to_empty_list():
    check = SelfCheckResult(
        authority_confidence="high",
        letter_type_confidence="high",
        deadline_confidence="high",
        required_actions_confidence="high",
        required_documents_confidence="high",
        consequences_confidence="high",
        contact_info_confidence="high",
        needs_human_review=False,
    )
    assert check.reasoning == []


def test_extraction_edit_request_allows_a_completely_empty_partial_update():
    # PATCH /letters/{id} relies on every field here being optional, so a user can send
    # just the one field they actually changed
    edit = ExtractionEditRequest()
    assert edit.model_dump(exclude_unset=True) == {}


def test_extraction_edit_request_still_validates_the_fields_it_is_given():
    with pytest.raises(ValidationError):
        ExtractionEditRequest(letter_type="not_a_real_type")