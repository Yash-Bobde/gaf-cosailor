"""Typed pipeline-stage errors and error-message sanitization.

A stage that cannot produce trustworthy output raises a typed error instead of
returning an empty "success" value, so the pipeline can record an honest state:

  ScrapeError   — the GAF capture / Coveo response could not be trusted
  ResearchError — web research produced no usable evidence

Every message that is stored in the database or shown to a rep goes through
sanitize_error() first: bearer tokens, API keys, cookies and long bodies are
stripped, and the text is truncated.
"""
import re

_MAX_LEN = 300

_SECRET_PATTERNS = [
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [redacted]"),
    (re.compile(r"(?i)(authorization|cookie|set-cookie|api[_-]?key|token)\s*[:=]\s*\S+"),
     r"\1=[redacted]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"), "[redacted-key]"),
    (re.compile(r"\bpplx-[A-Za-z0-9_-]{8,}"), "[redacted-key]"),
    (re.compile(r"\beyJ[A-Za-z0-9._-]{10,}"), "[redacted-jwt]"),
]


def sanitize_error(text: object, limit: int = _MAX_LEN) -> str:
    """Return a single-line, secret-free, length-bounded version of an error message."""
    message = " ".join(str(text or "").split())
    for pattern, replacement in _SECRET_PATTERNS:
        message = pattern.sub(replacement, message)
    return message if len(message) <= limit else message[: limit - 1] + "…"


class PipelineStageError(Exception):
    """Base class: a pipeline stage failed and its output must not be used."""

    stage = "pipeline"

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(sanitize_error(message))
        self.retryable = retryable


class ScrapeError(PipelineStageError):
    """The GAF locator capture or its Coveo response failed or was malformed."""

    stage = "scrape"


class ResearchError(PipelineStageError):
    """Web research failed or returned no usable evidence for a lead."""

    stage = "research"


def public_error(exc: BaseException) -> str:
    """Map any exception to a sanitized message fit for the database and the UI."""
    if isinstance(exc, PipelineStageError):
        return str(exc)
    if isinstance(exc, TimeoutError):
        return "Timed out before the lead finished processing"
    detail = sanitize_error(exc)
    return f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__
