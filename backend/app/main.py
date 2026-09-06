# FastAPI entrypoints
import uuid
import os
import tempfile
from ics import Calendar, Event
from datetime import date
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.db import init_db
from app.db import get_db
from app.models import User, Letter, Job, Extraction
from app.auth import (
    SignupRequest,
    Token,
    create_access_token,
    hash_password,
    verify_password,
    get_current_user,
)
from app.pipeline.classify_extract import classify_and_extract
from app.queue import letter_queue
from app.schemas import JobOut, UploadResponse, ApproveResponse
from app.worker import process_letter_job

from app.priority import build_letter_priority, detect_conflicts
from app.schemas import PrioritiesResponse, LetterPriorityOut, ConflictOut

UPLOADS_DIR = Path(__file__).resolve().parent.parent / "uploads"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="Bureaucracy Navigator API",
    description="Agentic pipeline for German bureaucracy letters.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/")
def root():
    """Liveness check --if this returns, container is up and FASTAPI is serving"""
    return {"status": "ok", "services": "bureaucracy-navigator_api"}


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/letters", response_model=UploadResponse)
async def upload_letter(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    if file.content_type != "image/png":
        raise HTTPException(
            status_code=400,
            detail=f"expected a PNG image, got content_type={file.content_type!r}",
        )
    image_bytes = await file.read()

    image_path = UPLOADS_DIR / f"{uuid.uuid4().hex}.png"
    image_path.write_bytes(image_bytes)

    letter = Letter(user_id=current_user.id, image_path=str(image_path))
    db.add(letter)
    db.commit()
    db.refresh(letter)

    job = Job(letter_id=letter.id, status="queued")
    db.add(job)
    db.commit()
    db.refresh(job)

    letter_queue.enqueue(process_letter_job, letter.id)
    return UploadResponse(letter_id=letter.id, job_id=job.id, status=job.status)


@app.get("/job/{job_id}", response_model=JobOut)
def get_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.get(Job, job_id)
    if job is None or job.letter.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="job not found")
    return JobOut.model_validate(job)


@app.post("/auth/signup", response_model=Token)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="email already registered")

    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return Token(access_token=create_access_token(user.id))


@app.post("/auth/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == form_data.username).first()
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(user.id))


@app.get("/priorities", response_model=PrioritiesResponse)
def get_priorities(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    extractions = (
        db.query(Extraction)
        .join(Letter, Extraction.letter_id == Letter.id)
        .filter(Letter.user_id == current_user.id)
        .filter(Extraction.approved == False)
        .all()
    )
    today = date.today()
    priorities = [
        p
        for p in (build_letter_priority(e, today) for e in extractions)
        if p is not None
    ]
    priorities.sort(key=lambda p: p.score, reverse=True)

    conflicts = detect_conflicts(priorities)

    return PrioritiesResponse(
        queue=[LetterPriorityOut.model_validate(p) for p in priorities],
        conflicts=[ConflictOut.model_validate(c) for c in conflicts],
    )


@app.post("/letters/{letter_id}/approve", response_model=ApproveResponse)
def approve_letter(
    letter_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    letter = db.get(Letter, letter_id)
    if letter is None or letter.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="letter not found")

    extraction = letter.extraction
    if extraction is None:
        raise HTTPException(status_code=409, detail="letter has not been extracted yet")

    if not extraction.approved:
        extraction.approved = True
        db.commit()

    return ApproveResponse(letter_id=letter.id, approved=True)


@app.get("letters/{letter_id}/ics")
def get_letter_ics(
    letter_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    letter = db.get(Letter, letter_id)
    if letter is None or letter.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="letter not found")

    extraction = letter.extraction
    if extraction is None:
        raise HTTPException(status_code=409, detail="letter has not been extracted yet")

    if not extraction.approved:
        raise HTTPException(status_code=409, detail="letter has not been approved yet")

    if not extraction.deadlines:
        raise HTTPException(
            status_code=404, detail="this letter has no deadlines to export"
        )

    calendar = Calendar()
    for i, entry in enumerate(extraction.deadlines):
        event = Event(
            name=f"{extraction.authority}: {entry['description']}",
            begin=entry["date"],
            uid=f"letter-{letter_id}-deadline-{i}@bureaucracy-navigator",
            description=extraction.consequences,
        )
        event.make_all_day()
        calendar.events.add(event)

    return Response(
        content=calendar.serialize(),
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="letter_{letter_id}.ics"'
        },
    )
