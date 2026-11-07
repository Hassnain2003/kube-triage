from __future__ import annotations

import pytest
from pydantic import ValidationError

from kube_triage.report import DiagnosisReport, EvidenceItem


def test_report_schema_accepts_valid_payload() -> None:
    report = DiagnosisReport(
        root_cause_category="crashloop_bad_config",
        explanation="bad config",
        evidence=[
            EvidenceItem(
                tool="list_pods",
                source_ref="list_pods:1",
                excerpt="CrashLoopBackOff",
            )
        ],
        suggested_fix="--- a/cm\n+++ b/cm\n",
        confidence=0.9,
    )
    assert report.tool_calls == 0


def test_report_rejects_bad_category() -> None:
    with pytest.raises(ValidationError):
        DiagnosisReport(
            root_cause_category="not-a-category",  # type: ignore[arg-type]
            explanation="x",
            evidence=[EvidenceItem(tool="t", source_ref="t:1", excerpt="e")],
            suggested_fix="none",
            confidence=0.1,
        )


def test_report_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        DiagnosisReport(
            root_cause_category="unknown",
            explanation="x",
            evidence=[],
            suggested_fix="none",
            confidence=0.0,
        )
