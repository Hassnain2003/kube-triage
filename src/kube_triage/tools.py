"""Read-only Kubernetes inspection tools shared by the MCP server and the agent."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import yaml

from kube_triage.redaction import redact, redact_text

Runner = Callable[..., str]

WRITE_VERBS = frozenset({"create", "update", "delete", "patch", "apply", "replace"})


class ClusterTools:
    def __init__(self, runner: Runner) -> None:
        self._runner = runner
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _call(self, name: str, args: dict[str, Any], kubectl_args: list[str]) -> str:
        if any(verb in kubectl_args for verb in WRITE_VERBS):
            raise PermissionError("write verbs are not allowed")
        self.calls.append((name, args))
        return self._runner(kubectl_args)

    def list_pods(self, namespace: str) -> str:
        return self._call(
            "list_pods",
            {"namespace": namespace},
            ["get", "pods", "-n", namespace, "-o", "wide"],
        )

    def describe_pod(self, namespace: str, name: str) -> str:
        return self._call(
            "describe_pod",
            {"namespace": namespace, "name": name},
            ["describe", "pod", name, "-n", namespace],
        )

    def get_events(self, namespace: str) -> str:
        return self._call(
            "get_events",
            {"namespace": namespace},
            ["get", "events", "-n", namespace, "--sort-by=.lastTimestamp"],
        )

    def get_logs(
        self,
        namespace: str,
        name: str,
        *,
        tail: int = 100,
        previous: bool = False,
    ) -> str:
        args = ["logs", name, "-n", namespace, f"--tail={tail}"]
        if previous:
            args.append("--previous")
        return self._call(
            "get_logs",
            {"namespace": namespace, "name": name, "tail": tail, "previous": previous},
            args,
        )

    def get_deployment(self, namespace: str, name: str) -> str:
        return self._call(
            "get_deployment",
            {"namespace": namespace, "name": name},
            ["get", "deployment", name, "-n", namespace, "-o", "yaml"],
        )

    def get_configmap(self, namespace: str, name: str) -> str:
        raw = self._call(
            "get_configmap",
            {"namespace": namespace, "name": name},
            ["get", "configmap", name, "-n", namespace, "-o", "yaml"],
        )
        try:
            parsed = yaml.safe_load(raw) or {}
        except yaml.YAMLError:
            return redact_text(raw)
        redacted = redact(parsed)
        return yaml.safe_dump(redacted, sort_keys=False)

    def get_service_endpoints(self, namespace: str, name: str) -> str:
        svc = self._call(
            "get_service_endpoints",
            {"namespace": namespace, "name": name},
            ["get", "service", name, "-n", namespace, "-o", "yaml"],
        )
        try:
            endpoints = self._runner(["get", "endpoints", name, "-n", namespace, "-o", "yaml"])
        except Exception as exc:  # noqa: BLE001 - surface missing endpoints as data
            endpoints = f"endpoints unavailable: {exc}"
        return f"{svc}\n---\n{endpoints}"


def tool_specs() -> list[dict[str, Any]]:
    """JSON-schema-ish descriptions used by the verify node."""
    return [
        {
            "name": "list_pods",
            "args": {"namespace": "str"},
        },
        {
            "name": "describe_pod",
            "args": {"namespace": "str", "name": "str"},
        },
        {
            "name": "get_events",
            "args": {"namespace": "str"},
        },
        {
            "name": "get_logs",
            "args": {
                "namespace": "str",
                "name": "str",
                "tail": "int",
                "previous": "bool",
            },
        },
        {
            "name": "get_deployment",
            "args": {"namespace": "str", "name": "str"},
        },
        {
            "name": "get_configmap",
            "args": {"namespace": "str", "name": "str"},
        },
        {
            "name": "get_service_endpoints",
            "args": {"namespace": "str", "name": "str"},
        },
    ]


def dispatch(tools: ClusterTools, name: str, arguments: dict[str, Any]) -> str:
    if name == "list_pods":
        return tools.list_pods(arguments["namespace"])
    if name == "describe_pod":
        return tools.describe_pod(arguments["namespace"], arguments["name"])
    if name == "get_events":
        return tools.get_events(arguments["namespace"])
    if name == "get_logs":
        return tools.get_logs(
            arguments["namespace"],
            arguments["name"],
            tail=int(arguments.get("tail", 100)),
            previous=bool(arguments.get("previous", False)),
        )
    if name == "get_deployment":
        return tools.get_deployment(arguments["namespace"], arguments["name"])
    if name == "get_configmap":
        return tools.get_configmap(arguments["namespace"], arguments["name"])
    if name == "get_service_endpoints":
        return tools.get_service_endpoints(arguments["namespace"], arguments["name"])
    raise ValueError(f"unknown tool: {name}")


def parse_pod_names(list_pods_output: str) -> list[str]:
    names: list[str] = []
    for line in list_pods_output.splitlines()[1:]:
        parts = line.split()
        if parts:
            names.append(parts[0])
    return names


def json_dumps(data: Any) -> str:
    return json.dumps(data, indent=2)
