from datetime import date
from types import SimpleNamespace

import pytest

from app.priority import (
    BASE_SEVERITY,
    MAX_SEVERITY,
    build_letter_priority,
    compute_severity,
    compute_urgency,
    days_until,
    detect_conflicts,
    earliest_deadline,
    priority_score,
)

from app.schemas import LetterType


def make_extraction(
    letter_id=1,
    authority="Finanzamt",
    letter_type="fee_tax_notice",
    deadlines=None,
    consequences=None,
    required_documents=None,
    required_actions=None,
):
    return SimpleNamespace(
        letter_id=letter_id,
        authority=authority,
        letter_type=letter_type,
        deadlines=deadlines if deadlines is not None else [],
        consequences=consequences,
        required_documents=required_documents if required_documents is not None else [],
        required_actions=required_actions if required_actions is not None else [],
    )


# Test for severity computation


def test_severity_uses_base_tier_for_each_letter_type():
    for letter_type, expected in BASE_SEVERITY.items():
        assert compute_severity(letter_type, consequences=None) == expected


def test_severity_bumps_once_on_keyword_match():
    result = compute_severity(
        LetterType.DOCUMENT_REQUEST, "Failure to comply may result in a fine."
    )
    assert result == BASE_SEVERITY[LetterType.DOCUMENT_REQUEST] + 1


def test_severity_with_no_consequences_text_stays_at_base():
    assert (
        compute_severity(LetterType.FEE_TAX_NOTICE, None)
        == BASE_SEVERITY[LetterType.FEE_TAX_NOTICE]
    )


def test_severity_bump_is_case_insensitive():
    result = compute_severity(
        LetterType.APPOINTMENT_NOTICE, "Your permit may be REVOKED."
    )
    assert result == BASE_SEVERITY[LetterType.APPOINTMENT_NOTICE] + 1


def test_severity_does_not_double_bump_for_multiple_keywords():
    text = (
        "Your visa may be revoked, you may face a fine, or be subject to deportation."
    )
    result = compute_severity(LetterType.INFORMATIONAL, text)
    assert result == BASE_SEVERITY[LetterType.INFORMATIONAL] + 1


def test_severity_caps_at_max_even_with_keyword():
    result = compute_severity(LetterType.DEADLINE_WARNING, "This may result in a fine.")
    assert result == MAX_SEVERITY


# Tests for urgency computation


def test_days_until_future_and_past():
    today = date(2026, 9, 5)
    assert days_until(date(2026, 9, 15), today) == 10
    assert days_until(date(2026, 9, 1), today) == -4


@pytest.mark.parametrize(
    "days_left,expected",
    [
        (-5, 100),  # overdue -- flat cap, not scaled by how overdue
        (0, 100),  # due today -- same treatment as overdue
        (1, 99),
        (50, 50),
        (150, 0),  # far out -- floors at 0, never goes negative
    ],
)
def test_compute_urgency(days_left, expected):
    assert compute_urgency(days_left) == expected


# tests for combined scores.


def test_priority_score_multiplies_severity_and_urgency():
    assert priority_score(severity=4, urgency=86) == 344


def test_priority_score_lets_severity_outrank_raw_urgency():
    urgent_but_harmless = priority_score(severity=1, urgency=100)
    severe_but_not_urgent = priority_score(severity=4, urgency=40)
    assert severe_but_not_urgent > urgent_but_harmless


# deadlines


def test_earliest_deadline_picks_the_soonest_date():
    deadlines = [
        {"date": "2026-10-01", "description": "pay fee"},
        {"date": "2026-09-20", "description": "submit form"},
        {"date": "2026-11-01", "description": "follow-up"},
    ]
    assert earliest_deadline(deadlines)["description"] == "submit form"


def test_earliest_deadline_empty_list_returns_none():
    assert earliest_deadline([]) is None


def test_build_letter_priority_informational_with_no_deadline_returns_none():
    extraction = make_extraction(letter_type="informational", deadlines=[])
    assert build_letter_priority(extraction, today=date(2026, 9, 5)) is None


def test_build_letter_priority_assembles_all_fields_correctly():
    extraction = make_extraction(
        letter_id=7,
        letter_type="fee_tax_notice",
        deadlines=[
            {"date": "2026-10-01", "description": "pay fee"},
            {"date": "2026-09-20", "description": "submit form"},
        ],
        consequences="Unpaid amounts are sent to collections.",
        required_documents=["Steuer-ID"],
    )
    result = build_letter_priority(extraction, today=date(2026, 9, 5))

    assert result.letter_id == 7
    assert result.deadline_date == date(2026, 9, 20)
    assert result.deadline_description == "submit form"
    assert result.days_left == 15
    assert result.severity == 4  # base 3 + collections keyword
    assert result.urgency == 85
    assert result.score == 4 * 85
    assert result.required_documents == ["Steuer-ID"]


# detecting conflicts


def priority_at(
    letter_id, deadline_date, required_documents=None, required_actions=None
):

    from app.priority import LetterPriority

    return LetterPriority(
        letter_id=letter_id,
        authority="Ausländerbehörde",
        letter_type=LetterType.DOCUMENT_REQUEST,
        deadline_date=deadline_date,
        deadline_description="test",
        days_left=0,
        severity=2,
        urgency=100,
        score=200,
        required_documents=required_documents or [],
        required_actions=required_actions or [],
    )


def test_detect_conflicts_flags_deadlines_within_window():
    a = priority_at(1, date(2026, 9, 20))
    b = priority_at(2, date(2026, 9, 22))  # 2 days apart, window is 3
    conflicts = detect_conflicts([a, b])
    assert len(conflicts) == 1
    assert conflicts[0].reason == "overlapping_deadlines"


def test_detect_conflicts_boundary_at_exactly_window_days_still_flags():

    a = priority_at(1, date(2026, 9, 20))
    b = priority_at(2, date(2026, 9, 23))  # exactly 3 days apart
    conflicts = detect_conflicts([a, b], window_days=3)
    assert len(conflicts) == 1


def test_detect_conflicts_outside_window_not_flagged():
    a = priority_at(1, date(2026, 9, 20))
    b = priority_at(2, date(2026, 9, 24))  # 4 days apart, outside window of 3
    conflicts = detect_conflicts([a, b], window_days=3)
    assert conflicts == []


def test_detect_conflicts_shared_requirement_takes_priority_over_generic_label():
    a = priority_at(1, date(2026, 9, 20), required_documents=["Meldebescheinigung"])
    b = priority_at(
        2, date(2026, 9, 22), required_documents=["meldebescheinigung"]
    )  # different case
    conflicts = detect_conflicts([a, b])
    assert len(conflicts) == 1
    assert conflicts[0].reason == "shared_requirement"
    assert "meldebescheinigung" in conflicts[0].detail


def test_detect_conflicts_no_pairs_for_single_letter():
    assert detect_conflicts([priority_at(1, date(2026, 9, 20))]) == []


def test_detect_conflicts_empty_list():
    assert detect_conflicts([]) == []
