from __future__ import annotations

from kube_triage.eval_harness import _score
from kube_triage.report import DiagnosisReport, EvidenceItem


def test_score_requires_category_and_evidence() -> None:
    report = DiagnosisReport(
        root_cause_category="crashloop_bad_config",
        explanation="bad config",
        evidence=[
            EvidenceItem(tool="list_pods", source_ref="list_pods:1", excerpt="CrashLoopBackOff")
        ],
        suggested_fix="revert the configmap flag",
        confidence=0.7,
    )
    golden = {
        "root_cause_category": "crashloop_bad_config",
        "required_evidence": ["CrashLoopBackOff", "CRASH_ON_START"],
    }
    correct, evidence_ok = _score(report, golden)
    assert correct is True
    assert evidence_ok is False

    report.explanation = "CRASH_ON_START=1 caused CrashLoopBackOff"
    correct, evidence_ok = _score(report, golden)
    assert correct is True
    assert evidence_ok is True
