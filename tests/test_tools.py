from __future__ import annotations

import pytest

from kube_triage.redaction import REDACTED
from kube_triage.tools import ClusterTools, dispatch
from tests.conftest import recorded_runner


def test_list_pods(tools: ClusterTools) -> None:
    out = tools.list_pods("demo")
    assert "CrashLoopBackOff" in out
    assert tools.calls[0][0] == "list_pods"


def test_describe_pod(tools: ClusterTools) -> None:
    assert "CrashLoopBackOff" in tools.describe_pod("demo", "orders-1")


def test_get_events(tools: ClusterTools) -> None:
    assert "BackOff" in tools.get_events("demo")


def test_get_logs_previous(tools: ClusterTools) -> None:
    out = tools.get_logs("demo", "orders-1", tail=50, previous=True)
    assert "CRASH_ON_START" in out
    assert tools.calls[-1][1]["previous"] is True


def test_get_deployment(tools: ClusterTools) -> None:
    assert "kube-triage-orders:dev" in tools.get_deployment("demo", "orders")


def test_get_configmap_redacts_secret_like_keys(tools: ClusterTools) -> None:
    out = tools.get_configmap("demo", "orders-config")
    assert "CRASH_ON_START" in out
    assert "super-secret-value" not in out
    assert "hunter2" not in out
    assert REDACTED in out


def test_get_service_endpoints(tools: ClusterTools) -> None:
    out = tools.get_service_endpoints("demo", "orders")
    assert "kind: Service" in out


def test_dispatch_unknown_tool(tools: ClusterTools) -> None:
    with pytest.raises(ValueError, match="unknown tool"):
        dispatch(tools, "delete_pod", {"namespace": "demo"})


def test_write_verbs_blocked() -> None:
    def runner(args: list[str]) -> str:
        return ""

    tools = ClusterTools(runner)
    with pytest.raises(PermissionError):
        tools._call("bad", {}, ["delete", "pod", "x", "-n", "demo"])


def test_recorded_runner_rejects_unexpected() -> None:
    with pytest.raises(AssertionError):
        recorded_runner(["get", "secrets"])
