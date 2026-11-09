from __future__ import annotations

from kube_triage.redaction import REDACTED, redact, redact_text


def test_redact_nested_keys() -> None:
    data = {"data": {"REDIS_HOST": "redis", "password": "hunter2", "nested": {"api_key": "abc"}}}
    out = redact(data)
    assert out["data"]["REDIS_HOST"] == "redis"
    assert out["data"]["password"] == REDACTED
    assert out["data"]["nested"]["api_key"] == REDACTED


def test_redact_text_assignments() -> None:
    text = "REDIS_HOST=redis\nTOKEN=abcd\nOK=1"
    out = redact_text(text)
    assert "TOKEN=" + REDACTED in out
    assert "REDIS_HOST=redis" in out
