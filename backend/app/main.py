# FastAPI entrypoints
import os
import tempfile
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import ValidationError

from app.db import init_db
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
# TODO GET /jobs{id}, POST /auth/signup, POST /auth/login
# TODO GET /priorities
# TODO POST /letters/{id}/approve
