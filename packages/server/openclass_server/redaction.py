"""Redaction helpers for safe display/log copies of customer text.

The original observation content is retained under the project retention policy;
anything derived for logs, events, or list previews must pass through redact().
"""

from __future__ import annotations

import re
from typing import Any

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s-]?)?(?:\(\d{2,4}\)[\s-]?)?\d{3,4}[\s-]?\d{3,4}(?!\d)")
CREDIT_CARD = re.compile(r"\b(?:\d[ -]?){13,16}\b")
SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
SECRET_TOKEN = re.compile(
    r"\b(?:sk|pk|api|bearer|token|oc_dev)[-_]?(?:key|token)?[A-Za-z0-9_-]{12,}\b",
    re.IGNORECASE,
)

_DEFAULT_PATTERNS: tuple[re.Pattern[str], ...] = (CREDIT_CARD, SSN, EMAIL, PHONE, SECRET_TOKEN)


def configured_blocklist(raw: str) -> tuple[str, ...]:
    """Parse comma-separated blocklist terms from Settings.redaction_blocklist."""
    if not raw.strip():
        return ()
    return tuple(term.strip() for term in raw.split(",") if term.strip())


def redact_text(
    text: str,
    blocklist: tuple[str, ...] = (),
    *,
    enabled: bool = True,
    extra_patterns: tuple[re.Pattern[str], ...] = (),
) -> str:
    """Return a redacted copy of text; the input is never modified."""
    if not enabled:
        return text
    redacted = text
    for term in blocklist:
        if term.strip():
            redacted = redacted.replace(term, "[redacted]")
    for pattern in (*_DEFAULT_PATTERNS, *extra_patterns):
        redacted = pattern.sub("[redacted]", redacted)
    return redacted


def _redact_value(value: Any, blocklist: tuple[str, ...], *, enabled: bool = True) -> Any:
    if not enabled:
        return value
    if isinstance(value, str):
        return redact_text(value, blocklist, enabled=enabled)
    if isinstance(value, dict):
        return redact_mapping(value, blocklist, enabled=enabled)
    if isinstance(value, list):
        return [_redact_value(item, blocklist, enabled=enabled) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item, blocklist, enabled=enabled) for item in value)
    return value


def redact_mapping(
    mapping: dict[str, Any], blocklist: tuple[str, ...] = (), *, enabled: bool = True
) -> dict[str, Any]:
    """Recursively redact every string value inside a JSON-like mapping."""
    if not enabled:
        return dict(mapping)
    return {key: _redact_value(value, blocklist, enabled=enabled) for key, value in mapping.items()}
