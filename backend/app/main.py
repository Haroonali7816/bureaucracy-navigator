# FastAPI entrypoints
import uuid
import os
import tempfile
import threading
from datetime import date
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, Response
from fastapi.middleware.cors import CORSMiddleware
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
from rq import SimpleWorker
from rq.timeouts import TimerDeathPenalty
from app.queue import letter_queue, redis_conn
from app.schemas import JobOut, UploadResponse, ApproveResponse, DraftReplyOut
from app.schemas import LetterListItemOut, LetterDetailOut, ExtractionEditRequest
from app.worker import process_letter_job
from app.pipeline.draft_reply import generate_draft_reply
from app.ics_builder import build_ics

from app.priority import build_letter_priority, detect_conflicts
from app.schemas import PrioritiesResponse, LetterPriorityOut, ConflictOut

UPLOADS_DIR = Path(__file__).resolve().parent.parent / "uploads"


class ThreadWorker(SimpleWorker):

    death_penalty_class = TimerDeathPenalty

    def _install_signal_handlers(self):
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    # Free-tier deployment accommodation (see docs/deployment notes): Render's free tier has
    # no separate slot for a background worker process, unlike docker-compose's dedicated
    # `worker` service. When RUN_WORKER_IN_PROCESS=true is set (Render only -- never set
    # locally), start the same RQ worker loop as a background thread instead, so one free web
    # service does both jobs. `daemon=True` means this thread never blocks the process from
    # exiting; it's fine for it to just vanish on shutdown, since RQ requeues an interrupted job.
    if os.environ.get("RUN_WORKER_IN_PROCESS") == "true":
        def _run_worker_loop():
            ThreadWorker([letter_queue], connection=redis_conn).work()

        threading.Thread(target=_run_worker_loop, daemon=True, name="rq-worker").start()

    yield


app = FastAPI(
    title="Bureaucracy Navigator API",
    description="Agentic pipeline for German bureaucracy letters.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://bureaucracy-navigator-gamma.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


def _letter_detail(letter: Letter) -> LetterDetailOut:
    job = letter.job
    extraction = letter.extraction
    return LetterDetailOut(
        letter_id=letter.id,
        created_at=letter.created_at,
        job_status=job.status if job else "unknown",
        job_error_message=job.error_message if job else None,
        authority=extraction.authority if extraction else None,
        letter_type=extraction.letter_type if extraction else None,
        deadlines=extraction.deadlines if extraction else [],
        required_actions=extraction.required_actions if extraction else [],
        required_documents=extraction.required_documents if extraction else [],
        consequences=extraction.consequences if extraction else None,
        contact_info=extraction.contact_info if extraction else None,
        confidence_flags=extraction.confidence_flags if extraction else [],
        field_confidence=extraction.field_confidence if extraction else None,
        review_reasoning=extraction.review_reasoning if extraction else [],
        needs_human_review=extraction.needs_human_review if extraction else None,
        approved=extraction.approved if extraction else None,
        draft_reply=extraction.draft_reply if extraction else None,
    )


@app.get("/letters", response_model=list[LetterListItemOut])
def list_letters(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    letters = (
        db.query(Letter)
        .filter(Letter.user_id == current_user.id)
        .order_by(Letter.created_at.desc())
        .all()
    )
    return [
        LetterListItemOut(
            letter_id=letter.id,
            created_at=letter.created_at,
            job_status=letter.job.status if letter.job else "unknown",
            authority=letter.extraction.authority if letter.extraction else None,
            letter_type=letter.extraction.letter_type if letter.extraction else None,
            needs_human_review=letter.extraction.needs_human_review if letter.extraction else None,
            approved=letter.extraction.approved if letter.extraction else None,
        )
        for letter in letters
    ]


@app.get("/letters/{letter_id}", response_model=LetterDetailOut)
def get_letter_detail(
    letter_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    letter = db.get(Letter, letter_id)
    if letter is None or letter.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="letter not found")
    return _letter_detail(letter)


@app.patch("/letters/{letter_id}", response_model=LetterDetailOut)
def edit_letter_extraction(
    letter_id: int,
    payload: ExtractionEditRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    letter = db.get(Letter, letter_id)
    if letter is None or letter.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="letter not found")

    extraction = letter.extraction
    if extraction is None:
        raise HTTPException(status_code=409, detail="letter has not been extracted yet")
    if extraction.approved:
        raise HTTPException(status_code=409, detail="letter already approved, cannot edit")

    updates = payload.model_dump(exclude_unset=True, mode="json")
    for field, value in updates.items():
        setattr(extraction, field, value)

    db.commit()
    db.refresh(letter)
    return _letter_detail(letter)


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


@app.get("/letters/{letter_id}/ics")
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

    ics_content = build_ics(
        letter_id=letter_id,
        authority=extraction.authority,
        consequences=extraction.consequences,
        deadlines=extraction.deadlines,
    )

    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="letter_{letter_id}.ics"'
        },
    )


@app.post("/letters/{letter_id}/draft", response_model=DraftReplyOut)
def create_letter_draft(
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

    if extraction.draft_reply is None:
        draft = generate_draft_reply(extraction)
        extraction.draft_reply = draft.model_dump(mode="json")
        db.commit()

    return DraftReplyOut(letter_id=letter_id, **extraction.draft_reply)
