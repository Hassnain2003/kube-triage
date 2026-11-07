from __future__ import annotations

from pathlib import Path

import pytest

from kube_triage.tools import ClusterTools

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def recorded_runner(args: list[str]) -> str:
    joined = " ".join(args)
    if args[:2] == ["get", "pods"]:
        return load("list_pods_crashloop.txt")
    if args[:2] == ["describe", "pod"]:
        return load("describe_pod_crashloop.txt")
    if args[:2] == ["get", "events"]:
        return load("events.txt")
    if args[:3] == ["get", "deployment", "orders"]:
        return load("deployment_orders.yaml")
    if args[:3] == ["get", "deployment", "worker"]:
        return load("deployment_worker.yaml")
    if args[:3] == ["get", "deployment", "redis"]:
        return load("deployment_redis.yaml")
    if args[:2] == ["get", "configmap"]:
        return load("configmap.yaml")
    if args[:2] == ["get", "service"]:
        return load("service_orders.yaml")
    if args[:2] == ["get", "endpoints"]:
        return load("service_orders.yaml")
    if args[:1] == ["logs"]:
        return load("injected_logs.txt")
    raise AssertionError(f"unexpected kubectl args: {joined}")


@pytest.fixture
def tools() -> ClusterTools:
    return ClusterTools(recorded_runner)
