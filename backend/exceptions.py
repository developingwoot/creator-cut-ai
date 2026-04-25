# backend/exceptions.py
#
# Canonical exception hierarchy for CreatorCutAI.
# All custom exceptions must be defined here.
# Never raise generic Exception in pipeline or route code — always use one of these.
#
# Referenced by: backend/CLAUDE.md, backend/pipeline/CLAUDE.md


class CreatorCutError(Exception):
    """Base exception for all CreatorCutAI errors.
    Catch this in route handlers to return structured HTTP errors."""
    pass


# ── Pipeline Errors ───────────────────────────────────────────────────────────────

class PipelineError(CreatorCutError):
    """A pipeline stage failed in a way that halts processing.
    Attach the failing stage name and clip_id where applicable."""
    def __init__(self, message: str, stage: str = None, clip_id: str = None):
        self.stage = stage
        self.clip_id = clip_id
        super().__init__(message)


class FFmpegError(PipelineError):
    """FFmpeg returned a non-zero exit code.
    Always include FFmpeg's stderr in the message so it's surfaced to the user."""
    def __init__(self, message: str, stderr: str = None, **kwargs):
        self.stderr = stderr
        full_message = f"{message}\nFFmpeg output:\n{stderr}" if stderr else message
        super().__init__(full_message, **kwargs)


class TranscriptionError(PipelineError):
    """Whisper failed to transcribe a clip.
    Pipeline continues with remaining clips — not a fatal error."""
    pass


class ClaudeAPIError(PipelineError):
    """Anthropic API returned an error or an unparseable response.
    Includes retry count so callers know if retries were exhausted."""
    def __init__(self, message: str, attempts: int = 1, **kwargs):
        self.attempts = attempts
        super().__init__(message, **kwargs)


class InvalidClaudeResponseError(ClaudeAPIError):
    """Claude returned a response that failed Pydantic validation.
    Attach the raw response for debugging."""
    def __init__(self, message: str, raw_response: str = None, **kwargs):
        self.raw_response = raw_response
        super().__init__(message, **kwargs)


class ProxyGenerationError(FFmpegError):
    """Proxy file could not be generated from the source clip."""
    pass


class FrameExtractionError(FFmpegError):
    """Frame extraction failed — FFmpeg scene detection or sampling error."""
    pass


class OllamaUnreachableError(PipelineError):
    """Ollama HTTP server is not reachable at the configured host.
    Raised after auto-spawn attempt fails or connection is refused."""
    def __init__(self, host: str = "http://127.0.0.1:11434"):
        self.host = host
        super().__init__(
            f"Ollama is not reachable at {host}. "
            f"Install Ollama from https://ollama.com/download and ensure it is running.",
            stage="ollama",
        )


class OllamaModelMissingError(PipelineError):
    """A required Ollama model is not installed locally."""
    def __init__(self, model: str):
        self.model = model
        super().__init__(
            f"Ollama model '{model}' is not installed. "
            f"Pull it with: ollama pull {model}",
            stage="ollama",
        )


class InvalidOllamaResponseError(PipelineError):
    """Ollama returned a response that failed JSON parsing or Pydantic validation."""
    def __init__(self, message: str, raw_response: str | None = None, **kwargs):
        self.raw_response = raw_response
        super().__init__(message, **kwargs)


class SingleClipNotProcessedError(PipelineError):
    """Single-clip apply was called before the process step completed."""
    def __init__(self, clip_id: str):
        super().__init__(
            f"Clip {clip_id} has not been processed yet — run the process step first.",
            stage="single_clip_apply",
            clip_id=clip_id,
        )


class AssemblyError(PipelineError):
    """Final video assembly failed.
    Distinguish between segment-level failures and concat failures."""
    def __init__(self, message: str, segment_order: int = None, **kwargs):
        self.segment_order = segment_order
        super().__init__(message, **kwargs)


# ── Storage / File System Errors ──────────────────────────────────────────────────

class StorageError(CreatorCutError):
    """File system or storage operation failed."""
    pass


class InsufficientDiskSpaceError(StorageError):
    """Not enough disk space to proceed.
    Always include required_gb and available_gb so the UI can display them."""
    def __init__(self, required_gb: float, available_gb: float):
        self.required_gb = required_gb
        self.available_gb = available_gb
        super().__init__(
            f"Need {required_gb:.1f}GB free, but only {available_gb:.1f}GB available. "
            f"Free up disk space and try again."
        )


class ClipNotFoundError(StorageError):
    """A clip file referenced by the database no longer exists on disk."""
    def __init__(self, clip_id: str, expected_path: str):
        self.clip_id = clip_id
        self.expected_path = expected_path
        super().__init__(
            f"Clip {clip_id} not found at {expected_path}. "
            f"The file may have been moved or deleted."
        )


class PipelineLockError(StorageError):
    """Another pipeline is already running for this project."""
    def __init__(self, project_id: str):
        self.project_id = project_id
        super().__init__(f"Pipeline already running for project {project_id}.")


# ── Validation Errors ─────────────────────────────────────────────────────────────

class InputValidationError(CreatorCutError):
    """Input data failed validation before entering the pipeline.
    These are user-fixable — show the message directly in the UI."""
    pass


class InvalidClipError(InputValidationError):
    """An uploaded clip file is invalid, corrupted, or uses an unsupported codec."""
    def __init__(self, filename: str, reason: str):
        self.filename = filename
        self.reason = reason
        super().__init__(f"'{filename}' cannot be processed: {reason}")


class UnsupportedCodecError(InvalidClipError):
    """The clip uses a codec CreatorCutAI cannot process."""
    def __init__(self, filename: str, codec: str):
        super().__init__(
            filename,
            f"Codec '{codec}' is not supported. Please transcode to H.264 or ProRes."
        )


class InvalidBriefError(InputValidationError):
    """The story brief failed validation — missing required fields or stale references."""
    pass


class PathTraversalError(InputValidationError):
    """A filename or path contains characters that could escape the project directory.
    This is a security check — fail hard, log loudly."""
    def __init__(self, filename: str):
        self.filename = filename
        super().__init__(
            f"Filename '{filename}' contains invalid characters. "
            f"Rename the file and try again."
        )


# ── Configuration Errors ──────────────────────────────────────────────────────────

class ConfigurationError(CreatorCutError):
    """Application is misconfigured. These are fatal — shown on startup."""
    pass


class APIKeyMissingError(ConfigurationError):
    """Anthropic API key is not configured. Triggers the setup wizard."""
    def __init__(self):
        super().__init__(
            "Anthropic API key not configured. "
            "Run CreatorCutAI setup or set ANTHROPIC_API_KEY environment variable."
        )


class FFmpegNotFoundError(ConfigurationError):
    """FFmpeg is not installed or not on PATH. Fatal — pipeline cannot function."""
    def __init__(self):
        super().__init__(
            "FFmpeg not found. Install it with:\n"
            "  macOS:  brew install ffmpeg\n"
            "  Ubuntu: sudo apt install ffmpeg\n"
            "  Windows: https://ffmpeg.org/download.html"
        )


# ── Usage Pattern ─────────────────────────────────────────────────────────────────
#
# In FastAPI route handlers, convert to HTTPException:
#
# @router.post("/{project_id}/analyze")
# async def start_analysis(project_id: str):
#     try:
#         await run_pipeline(project_id)
#     except InsufficientDiskSpaceError as e:
#         raise HTTPException(status_code=507, detail=str(e))
#     except InvalidClipError as e:
#         raise HTTPException(status_code=422, detail=str(e))
#     except PipelineLockError as e:
#         raise HTTPException(status_code=409, detail=str(e))
#     except PipelineError as e:
#         raise HTTPException(status_code=500, detail=str(e))
#
# In pipeline code, always raise a specific subclass — never bare Exception or CreatorCutError.
