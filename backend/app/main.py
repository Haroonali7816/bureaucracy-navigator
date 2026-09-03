# FastAPI entrypoints
import os
import tempfile
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.db import init_db
from app.db import get_db
from app.models import User
from app.auth import SignupRequest, Token, create_access_token, hash_password, verify_password
from app.pipeline.classify_extract import classify_and_extract

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
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

@app.post("/letters")
async def upload_letter(file:UploadFile = File(...)):

    if file.content_type != "image/png":
        raise HTTPException(
            status_code=400,
            detail=f"expected a PNG image, got content_type={file.content_type!r}"
        )
    image_bytes = await file.read()

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(image_bytes)
        tmp_path = tmp.name

    try:
        extraction = classify_and_extract(tmp_path)
    except ValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"extraction failed validation twice: {exc}",
        )
    finally:
        os.remove(tmp_path)

    return extraction.model_dump(mode="json")

@app.post("/auth/signup" , response_model = Token)
def signup(payload: SignupRequest, db : Session = Depends(get_db)):
    existing = db.query(User).filter(User.email ==payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="email already registered")

    user = User(email=payload.email, hashed_password=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return Token(access_token=create_access_token(user.id))

@app.post("/auth/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db:Session=Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if user is None or not verify_password(form_data.password,user.hashed_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(user.id))
# TODO GET /priorities
# TODO POST /letters/{id}/approve
