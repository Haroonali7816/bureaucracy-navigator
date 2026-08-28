# FastAPI entrypoints
from fastapi import FastAPI

app = FastAPI(
    title="Bureaucracy Navigator API",
    description="Agentic pipeline for German bureaucracy letters.",
    version="0.1.0"
)

@app.get("/")
def root():
    """Liveness check --if this returns, container is up and FASTAPI is serving"""
    return {"status": "ok", "services": "bureaucracy-navigator_api"}

@app.get("/health")
def health():
    return {"status": "healthy"}

# TODO POST /letters
# TODO GET /jobs{id}, POST /auth/signup, POST /auth/login
# TODO GET /priorities
# TODO POST /letters/{id}/approve
