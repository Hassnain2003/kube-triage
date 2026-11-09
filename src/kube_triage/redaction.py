"""Redact secret-like keys and values from cluster objects before prompting."""

from __future__ import annotations

import copy
import re
from typing import Any

SECRET_KEY_RE = re.compile(
    r"(secret|password|passwd|token|api[_-]?key|credential|private[_-]?key|auth)",
    re.IGNORECASE,
)
SECRET_VALUE_RE = re.compile(
    r"^(bearer\s+\S+|sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})$",
    re.IGNORECASE,
)
REDACTED = "***REDACTED***"


def redact(obj: Any) -> Any:
    """Return a copy with secret-like mapping keys and values removed."""
    return _redact(copy.deepcopy(obj))


def redact_text(text: str) -> str:
    """Redact lines that look like KEY=secret assignments in raw text."""
    lines = []
    for line in text.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            stripped_key = key.strip().strip('"').strip("'")
            if SECRET_KEY_RE.search(stripped_key):
                lines.append(f"{key}={REDACTED}")
                continue
            if SECRET_VALUE_RE.match(value.strip().strip('"').strip("'")):
                lines.append(f"{key}={REDACTED}")
                continue
        lines.append(line)
    return "\n".join(lines)


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: dict[Any, Any] = {}
        for key, value in obj.items():
            if isinstance(key, str) and SECRET_KEY_RE.search(key):
                out[key] = REDACTED
            else:
                out[key] = _redact(value)
        return out
    if isinstance(obj, list):
        return [_redact(item) for item in obj]
    if isinstance(obj, str) and SECRET_VALUE_RE.match(obj.strip()):
        return REDACTED
    return obj
