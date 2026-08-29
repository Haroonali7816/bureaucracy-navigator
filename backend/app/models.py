from datetime import datetime

from sqlalchemy import(
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    JSON,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True,nullable=False,index=True)
    hashed_password = Column(String,nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    letters = relationship("Letter", back_populates="user")

class Letter(Base):
    __tablename__ = "letters"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    source_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates= "letters")
    extraction = relationship("Extraction", back_populates= "letter", uselist=False)
    job = relationship("Job", back_populates= "letter", uselist=False)

class Extraction(Base):
    __tablename__ = "extractions"

    id = Column(Integer, primary_key=True)
    letter_id = Column(Integer, ForeignKey("letters.id"), nullable=False)

    authority = Column(String, nullable=False)
    letter_type = Column(String, nullable=False)
    deadlines = Column(JSON, default=list)
    required_actions = Column(JSON, default=list)
    required_documents = Column(JSON, default=list)
    consequences = Column(Text, nullable=True)
    contact_info = Column(Text, nullable=True)
    confidence_flags = Column(JSON, default=list)
    needs_human_review = Column(Boolean, default=False)
    approved = Column(Boolean, default=False)

    letter = relationship("Letter", back_populates="extraction")

class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    letter_id = Column(Integer, ForeignKey("letters.id"), nullable=False)
    status = Column(String, default="queued") # queued, processing, done, failed
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    letter = relationship("Letter", back_populates = "job")

    