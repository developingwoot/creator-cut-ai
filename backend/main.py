from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from loguru import logger

from config import key_manager, settings, validate_startup
from storage.database import create_tables
from storage.local import db_path


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("CreatorCutAI starting up...")
    validate_startup(settings, key_manager)
    create_tables(db_path(settings.base_dir))
    logger.info("Startup complete.")
    yield
    logger.info("CreatorCutAI shutting down.")


app = FastAPI(
    title="CreatorCutAI",
    description="AI-powered video editing for YouTube creators",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

from routes.projects import router as projects_router
from routes.upload import router as upload_router
from routes.analyze import router as analyze_router
from routes.assemble import router as assemble_router

app.include_router(projects_router, prefix="/api")
app.include_router(upload_router, prefix="/api")
app.include_router(analyze_router, prefix="/api")
app.include_router(assemble_router, prefix="/api")


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["meta"])
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


# ── Serve React build in production ──────────────────────────────────────────

_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="static")
