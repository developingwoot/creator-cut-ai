from __future__ import annotations

import re
from pathlib import Path

from exceptions import PathTraversalError


_SAFE_FILENAME = re.compile(r'^[\w\-. ]+$')


def assert_safe_filename(filename: str) -> None:
    """Reject filenames that could escape the project directory."""
    if not _SAFE_FILENAME.match(filename) or ".." in filename or "/" in filename:
        raise PathTraversalError(filename)


# ── Database ──────────────────────────────────────────────────────────────────

def db_path(base_dir: Path) -> Path:
    return base_dir / "projects.db"


# ── Project-level directories ─────────────────────────────────────────────────

def projects_root(base_dir: Path) -> Path:
    return base_dir / "projects"


def project_dir(base_dir: Path, project_id: str) -> Path:
    return projects_root(base_dir) / project_id


# ── Per-project subdirectories ────────────────────────────────────────────────

def clips_dir(base_dir: Path, project_id: str) -> Path:
    return project_dir(base_dir, project_id) / "clips"


def proxies_dir(base_dir: Path, project_id: str) -> Path:
    return project_dir(base_dir, project_id) / "proxies"


def frames_dir(base_dir: Path, project_id: str) -> Path:
    return project_dir(base_dir, project_id) / "frames"


def transcripts_dir(base_dir: Path, project_id: str) -> Path:
    return project_dir(base_dir, project_id) / "transcripts"


def outputs_dir(base_dir: Path, project_id: str) -> Path:
    return project_dir(base_dir, project_id) / "outputs"


def pipeline_lock_path(base_dir: Path, project_id: str) -> Path:
    return project_dir(base_dir, project_id) / ".pipeline.lock"


# ── Per-clip paths ────────────────────────────────────────────────────────────

def clip_path(base_dir: Path, project_id: str, filename: str) -> Path:
    assert_safe_filename(filename)
    return clips_dir(base_dir, project_id) / filename


def proxy_path(base_dir: Path, project_id: str, clip_id: str) -> Path:
    return proxies_dir(base_dir, project_id) / f"{clip_id}_proxy.mp4"


def transcript_path(base_dir: Path, project_id: str, clip_id: str) -> Path:
    return transcripts_dir(base_dir, project_id) / f"{clip_id}.json"


def frames_subdir(base_dir: Path, project_id: str, clip_id: str) -> Path:
    return frames_dir(base_dir, project_id) / clip_id


def output_path(base_dir: Path, project_id: str, filename: str = "output.mp4") -> Path:
    return outputs_dir(base_dir, project_id) / filename


def single_clip_output_path(base_dir: Path, project_id: str, clip_id: str) -> Path:
    return outputs_dir(base_dir, project_id) / f"{clip_id}_edited.mp4"


# ── Directory initialisation ──────────────────────────────────────────────────

def ensure_project_dirs(base_dir: Path, project_id: str) -> None:
    """Create all subdirectories for a new project."""
    for fn in (clips_dir, proxies_dir, frames_dir, transcripts_dir, outputs_dir):
        fn(base_dir, project_id).mkdir(parents=True, exist_ok=True)
