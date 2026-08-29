from datetime import date
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