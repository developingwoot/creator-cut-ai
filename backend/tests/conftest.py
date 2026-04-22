"""Shared pytest fixtures for backend tests."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def fixture_clip_path(tmp_path_factory) -> Path:
    """A 3-second synthetic MP4 generated with FFmpeg testsrc.

    Created once per test session. Requires FFmpeg on PATH.
    """
    out = tmp_path_factory.mktemp("fixtures") / "test_clip.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=3:size=1920x1080:rate=30",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-c:v", "libx264", "-crf", "28", "-preset", "ultrafast",
            "-c:a", "aac", "-shortest",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out
