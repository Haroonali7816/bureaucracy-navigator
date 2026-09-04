# FastAPI entrypoints
import uuid
import os
import tempfile
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.db import init_db
from app.db import get_db
from app.models import User, Letter, Job
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
from app.schemas import JobOut, UploadResponse
from app.worker import process_letter_job

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


# TODO GET /priorities
# TODO POST /letters/{id}/approve
