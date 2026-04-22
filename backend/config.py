from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from loguru import logger
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from exceptions import APIKeyMissingError, FFmpegNotFoundError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CREATORCUT_", env_file=".env", extra="ignore")

    base_dir: Path = Path.home() / ".creatorcut"
    port: int = 8000
    whisper_model: str = "medium"
    max_concurrent: int = 5
    log_level: str = "INFO"

    # Anthropic key is read separately via KeyManager — not in Settings —
    # because it may come from the OS keychain, not just env vars.
    anthropic_api_key: str = ""

    @field_validator("base_dir", mode="before")
    @classmethod
    def expand_base_dir(cls, v: str | Path) -> Path:
        return Path(v).expanduser().resolve()


class KeyManager:
    """Single source of truth for the Anthropic API key.

    Resolution order:
      1. ANTHROPIC_API_KEY environment variable
      2. OS keychain  (service="creatorcut-ai", username="api-key")
      3. ~/.creatorcut/config.json  {"anthropic_api_key": "sk-ant-..."}

    Raises APIKeyMissingError if no key is found.
    """

    _KEYCHAIN_SERVICE = "creatorcut-ai"
    _KEYCHAIN_USER = "api-key"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cached_key: str | None = None

    def get_key(self) -> str:
        if self._cached_key:
            return self._cached_key

        key = (
            self._from_env()
            or self._from_keychain()
            or self._from_config_file()
        )
        if not key:
            raise APIKeyMissingError()

        self._cached_key = key
        return key

    def store_key(self, key: str) -> None:
        """Persist key to OS keychain; fall back to config.json."""
        stored = self._store_in_keychain(key)
        if not stored:
            self._store_in_config_file(key)
        self._cached_key = key
        logger.info("API key stored successfully.")

    def _from_env(self) -> str | None:
        return os.environ.get("ANTHROPIC_API_KEY") or None

    def _from_keychain(self) -> str | None:
        try:
            result = subprocess.run(
                ["security", "find-generic-password",
                 "-s", self._KEYCHAIN_SERVICE,
                 "-a", self._KEYCHAIN_USER,
                 "-w"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip() or None
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return None

    def _store_in_keychain(self, key: str) -> bool:
        try:
            result = subprocess.run(
                ["security", "add-generic-password",
                 "-s", self._KEYCHAIN_SERVICE,
                 "-a", self._KEYCHAIN_USER,
                 "-w", key, "-U"],
                capture_output=True, timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _from_config_file(self) -> str | None:
        config_path = self._settings.base_dir / "config.json"
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text())
                return data.get("anthropic_api_key") or None
            except (json.JSONDecodeError, OSError):
                pass
        return None

    def _store_in_config_file(self, key: str) -> None:
        config_path = self._settings.base_dir / "config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        if config_path.exists():
            try:
                existing = json.loads(config_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        existing["anthropic_api_key"] = key
        config_path.write_text(json.dumps(existing, indent=2))
        config_path.chmod(0o600)


def validate_startup(settings: Settings, key_manager: KeyManager) -> None:
    """Run at application startup. Logs status for each dependency and raises on fatal failures."""
    errors: list[str] = []

    # FFmpeg
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"], capture_output=True, text=True, timeout=5
            )
            version_line = result.stdout.splitlines()[0] if result.stdout else "unknown"
            logger.info(f"[OK] FFmpeg: {version_line}")
        except subprocess.TimeoutExpired:
            logger.warning("[WARN] FFmpeg found but version check timed out")
    else:
        logger.error("[FAIL] FFmpeg not found — install it and re-run")
        errors.append("ffmpeg")

    # Anthropic API key
    try:
        key_manager.get_key()
        logger.info("[OK] API key configured")
    except APIKeyMissingError:
        logger.error("[FAIL] Anthropic API key not configured — set ANTHROPIC_API_KEY or run setup")
        errors.append("api_key")

    # Database directory
    db_path = settings.base_dir / "projects.db"
    try:
        settings.base_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[OK] Database at {db_path}")
    except OSError as exc:
        logger.error(f"[FAIL] Cannot create base directory {settings.base_dir}: {exc}")
        errors.append("base_dir")

    # SFX library
    sfx_manifest = Path(__file__).parent.parent / "assets" / "sfx" / "manifest.json"
    if sfx_manifest.exists():
        try:
            catalog = json.loads(sfx_manifest.read_text())
            count = len(catalog.get("sounds", []))
            logger.info(f"[OK] SFX library: {count} sounds")
        except (json.JSONDecodeError, OSError):
            logger.warning("[WARN] SFX manifest unreadable")
    else:
        logger.warning("[WARN] SFX manifest not found — sound design will be skipped")

    if errors:
        raise FFmpegNotFoundError() if "ffmpeg" in errors else APIKeyMissingError()


settings = Settings()
key_manager = KeyManager(settings)
