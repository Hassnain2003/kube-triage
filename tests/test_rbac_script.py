from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check_rbac.sh"


def test_rbac_script_denies_writes_and_secrets() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "kubectl auth can-i" in text
    for verb in ("create", "update", "delete", "patch"):
        assert f"expect_no {verb} pods" in text or f"expect_no {verb}" in text
    assert "expect_no get secrets" in text
    assert "expect_no list secrets" in text
    assert "expect_yes get pods" in text
