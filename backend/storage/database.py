from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

from loguru import logger
from sqlmodel import Session, SQLModel, create_engine, text

# Import all models so SQLModel registers their metadata before create_all.
import models.clip  # noqa: F401
import models.edit_plan  # noqa: F401
import models.project  # noqa: F401


_engine = None


def get_engine(db_path: Path):
    global _engine
    if _engine is None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{db_path}"
        _engine = create_engine(
            url,
            echo=False,
            connect_args={"check_same_thread": False},
        )
        with _engine.connect() as conn:
            conn.execute(text("PRAGMA journal_mode=WAL"))
            conn.execute(text("PRAGMA foreign_keys=ON"))
            conn.execute(text("PRAGMA synchronous=NORMAL"))
        logger.info(f"Database initialised at {db_path}")
    return _engine


def create_tables(db_path: Path) -> None:
    engine = get_engine(db_path)
    SQLModel.metadata.create_all(engine)
    logger.info("Database tables created (or already exist)")


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a database session per request."""
    if _engine is None:
        raise RuntimeError("Database engine not initialised — call create_tables() at startup")
    with Session(_engine) as session:
        yield session
