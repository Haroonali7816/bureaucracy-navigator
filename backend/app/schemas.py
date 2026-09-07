from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Authority(str, Enum):
    AUSLANDERBEHORDE = "Ausländerbehörde"
    FINANZAMT = "Finanzamt"
    KRANKENKASSE = "Krankenkasse"
    UNIVERSITAT = "University"
    BURGERAMT = "Bürgeramt"
    OTHER = "Other"


class LetterType(str, Enum):
    APPOINTMENT_NOTICE = "appointment_notice"
    FEE_TAX_NOTICE = "fee_tax_notice"
    DOCUMENT_REQUEST = "document_request"
    DEADLINE_WARNING = "deadline_warning"
    INFORMATIONAL = "informational"


class Deadline(BaseModel):
    date: date
    description: str


class ExtractionResult(BaseModel):
    authority: Authority
    letter_type: LetterType
    deadlines: list[Deadline] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    consequences: Optional[str] = None
    contact_info: Optional[str] = None
    confidence_flags: list[str] = Field(default_factory=list)


class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SelfCheckResult(BaseModel):
    authority_confidence: ConfidenceLevel
    letter_type_confidence: ConfidenceLevel
    deadline_confidence: ConfidenceLevel
    required_actions_confidence: ConfidenceLevel
    required_documents_confidence: ConfidenceLevel
    consequences_confidence: ConfidenceLevel
    contact_info_confidence: ConfidenceLevel
    needs_human_review: bool
    reasoning: list[str] = Field(default_factory=list)


class JobOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    letter_id: int
    status: str
    error_message: Optional[str] = None


class UploadResponse(BaseModel):
    letter_id: int
    job_id: int
    status: str

class LetterPriorityOut(BaseModel):
    model_config = {"from_attributes": True}

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

class ConflictOut(BaseModel):
    model_config = {"from_attributes": True}

    letter_id_a: int
    letter_id_b: int
    reason: str
    detail: str

class PrioritiesResponse(BaseModel):
    queue: list[LetterPriorityOut]
    conflicts: list[ConflictOut]

class ApproveResponse(BaseModel):
    letter_id: int
    approved: bool

class DraftReply(BaseModel):
    subject: str = Field(..., description="Short subject line, in German")
    body_de: str = Field(..., description="Full reply text, formal German (Sie-form), ready to send")
    summary_en: str = Field(..., description="2-3 plain English sentences explaining what body_de says")

class DraftReplyOut(BaseModel):
    letter_id: int
    subject: str
    body_de: str
    summary_en: str
class LetterListItemOut(BaseModel):
    model_config = {"from_attributes": True}

    letter_id: int
    created_at: datetime
    job_status: str
    authority: Optional[str] = None
    letter_type: Optional[str] = None
    needs_human_review: Optional[bool] = None
    approved: Optional[bool] = None


class LetterDetailOut(BaseModel):
    model_config = {"from_attributes": True}

    letter_id: int
    created_at: datetime
    job_status: str
    job_error_message: Optional[str] = None
    authority: Optional[str] = None
    letter_type: Optional[str] = None
    deadlines: list[Deadline] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    required_documents: list[str] = Field(default_factory=list)
    consequences: Optional[str] = None
    contact_info: Optional[str] = None
    confidence_flags: list[str] = Field(default_factory=list)
    field_confidence: Optional[dict] = None
    review_reasoning: list[str] = Field(default_factory=list)
    needs_human_review: Optional[bool] = None
    approved: Optional[bool] = None
    draft_reply: Optional[dict] = None


class ExtractionEditRequest(BaseModel):
    authority: Optional[Authority] = None
    letter_type: Optional[LetterType] = None
    deadlines: Optional[list[Deadline]] = None
    required_actions: Optional[list[str]] = None
    required_documents: Optional[list[str]] = None
    consequences: Optional[str] = None
    contact_info: Optional[str] = None
