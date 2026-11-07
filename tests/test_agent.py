from __future__ import annotations

from kube_triage.agent import SYSTEM_PROMPT, TriageAgent
from kube_triage.llm import FakeLLMProvider
from kube_triage.tools import ClusterTools
from kube_triage.untrusted import END, wrap_untrusted
from tests.conftest import recorded_runner


def test_untrusted_wrapper_present() -> None:
    block = wrap_untrusted("get_logs:1", "hello")
    assert "<<<UNTRUSTED_CLUSTER_DATA" in block
    assert END in block
    assert "untrusted" in SYSTEM_PROMPT.lower()


def test_step_budget_stops_gather() -> None:
    tools = ClusterTools(recorded_runner)
    agent = TriageAgent(tools, FakeLLMProvider(), max_tool_calls=2, timeout_seconds=30)
    report = agent.run()
    assert report.root_cause_category == "unknown"
    assert report.stopped_reason == "BudgetExceeded"
    assert len(tools.calls) <= 2
    assert report.tool_calls <= 2


def test_prompt_injection_in_logs_does_not_change_category() -> None:
    tools = ClusterTools(recorded_runner)
    llm = FakeLLMProvider()
    agent = TriageAgent(tools, llm, max_tool_calls=16, timeout_seconds=30)
    report = agent.run()
    assert report.root_cause_category == "crashloop_bad_config"
    assert report.root_cause_category != "imagepull_wrong_tag"
    assert len(tools.calls) <= 16
    assert "CrashLoopBackOff" in report.model_dump_json()
