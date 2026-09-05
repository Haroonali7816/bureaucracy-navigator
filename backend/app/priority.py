from __future__ import annotations

from datetime import date
from typing import Optional

from app.schemas import LetterType

from dataclasses import dataclass
from app.models import Extraction

# 1-4 severity scale levels
# deadline/ fee/tax is worse to ignore than appointment
# which is worse to ignore than informational letters.

BASE_SEVERITY: dict[LetterType, int] = {
    LetterType.DEADLINE_WARNING: 3,
    LetterType.FEE_TAX_NOTICE: 3,
    LetterType.DOCUMENT_REQUEST: 2,
    LetterType.APPOINTMENT_NOTICE: 2,
    LetterType.INFORMATIONAL: 1,
}

MAX_SEVERITY = 4

SEVERE_KEYWORDS = [
    "deport",
    "revoke",
    "revocation",
    "cancel",
    "cancellation",
    "terminate",
    "termination",
    "suspend",
    "expire",
    "expiration",
    "fine",
    "penalty",
    "collections",
    "legal action",
    "lawsuit",
    "criminal",
    # German
    "abschieben",
    "abschiebung",
    "widerruf",
    "widerrufen",
    "kündigung",
    "kündigen",
    "beendigung",
    "aussetzung",
    "erlischt",
    "erlöschen",
    "erloschen",
    "bußgeld",
    "geldstrafe",
    "strafe",
    "inkasso",
    "rechtliche schritte",
    "klage",
    "strafrechtlich",
]


def compute_severity(letter_type: LetterType, consequences: Optional[str]) -> int:
    """letter_type + consequences text -> an integer severity, 1 (least)
    to MAX_SEVERITY(Most severe)"""

    severity = BASE_SEVERITY[letter_type]

    if consequences:
        text = consequences.lower()
        if any(keyword in text for keyword in SEVERE_KEYWORDS):
            severity += 1
    return min(severity, MAX_SEVERITY)


# then we calculate the urgency of the letter.
def days_until(deadline: date, today: date) -> int:
    return (deadline - today).days


def compute_urgency(days_left: int) -> int:
    if days_left <= 0:
        return 100
    return max(0, 100 - days_left)


# now we combine the scores
def priority_score(severity: int, urgency: int) -> int:

    return severity * urgency


@dataclass
class LetterPriority:
    letter_id: int
    authority: str
    letter_type: LetterType
    deadline_date: date
    deadline_description: str
    days_left: int
    severity: int
    urgency: int
    score: int
    required_documents: list[str]
    required_actions: list[str]


def earliest_deadline(deadlines: list[dict]) -> Optional[dict]:
    if not deadlines:
        return None
    return min(deadlines, key=lambda d: d["date"])


def build_letter_priority(
    extraction: Extraction, today: date
) -> Optional[LetterPriority]:

    entry = earliest_deadline(extraction.deadlines)
    if entry is None:
        return None

    deadline_date = date.fromisoformat(entry["date"])
    letter_type = LetterType(extraction.letter_type)

    days_left = days_until(deadline_date, today)
    urgency = compute_urgency(days_left)
    severity = compute_severity(letter_type, extraction.consequences)
    score = priority_score(severity, urgency)

    return LetterPriority(
        letter_id=extraction.letter_id,
        authority=extraction.authority,
        letter_type=letter_type,
        deadline_date=deadline_date,
        deadline_description=entry["description"],
        days_left=days_left,
        severity=severity,
        urgency=urgency,
        score=score,
        required_documents=extraction.required_documents,
        required_actions=extraction.required_actions,
    )


CONFLICT_WINDOW_DAYS = 3


@dataclass
class Conflict:
    letter_id_a: int
    letter_id_b: int
    reason: str
    detail: str


def normalize(items: list[str]) -> set[str]:
    return {item.strip().lower() for item in items if item.strip()}


def shared_requirement(a: LetterPriority, b: LetterPriority) -> Optional[str]:
    shared_docs = normalize(a.required_documents) & normalize(b.required_documents)
    if shared_docs:
        return f"both need: {', '.join(sorted(shared_docs))}"
    shared_actions = normalize(a.required_actions) & normalize(b.required_actions)
    if shared_actions:
        return f"both require: {', '.join(sorted(shared_actions))}"

    return None


def detect_conflicts(
    priorities: list[LetterPriority],
    window_days: int = CONFLICT_WINDOW_DAYS,
) -> list[Conflict]:
    conflicts: list[Conflict] = []

    for i in range(len(priorities)):
        for j in range(i + 1, len(priorities)):
            a, b = priorities[i], priorities[j]
            gap = abs((a.deadline_date - b.deadline_date).days)

            if gap > window_days:
                continue

            shared = shared_requirement(a, b)
            if shared:
                conflicts.append(
                    Conflict(a.letter_id, b.letter_id, "shared_requirement", shared)
                )
            else:
                conflicts.append(
                    Conflict(
                        a.letter_id,
                        b.letter_id,
                        "overlapping_deadlines",
                        f"deadlines {gap} day(s) apart",
                    )
                )

    return conflicts
