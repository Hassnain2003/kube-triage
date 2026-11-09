"""Read-only MCP server exposing Kubernetes inspection tools."""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from kube_triage.kubectl import run_kubectl
from kube_triage.tools import ClusterTools

mcp = FastMCP("kube-triage")
_tools: ClusterTools | None = None


def get_tools() -> ClusterTools:
    global _tools
    if _tools is None:
        kubeconfig = os.environ.get("KUBECONFIG")

        def runner(args: list[str]) -> str:
            return run_kubectl(args, kubeconfig=kubeconfig)

        _tools = ClusterTools(runner)
    return _tools


@mcp.tool()
def list_pods(namespace: str = "demo") -> str:
    """List pods in a namespace (read-only)."""
    return get_tools().list_pods(namespace)


@mcp.tool()
def describe_pod(name: str, namespace: str = "demo") -> str:
    """Describe a single pod (read-only)."""
    return get_tools().describe_pod(namespace, name)


@mcp.tool()
def get_events(namespace: str = "demo") -> str:
    """List namespaced events (read-only)."""
    return get_tools().get_events(namespace)


@mcp.tool()
def get_logs(
    name: str,
    namespace: str = "demo",
    tail: int = 100,
    previous: bool = False,
) -> str:
    """Fetch container logs. Set previous=True for the last crashed container."""
    return get_tools().get_logs(namespace, name, tail=tail, previous=previous)


@mcp.tool()
def get_deployment(name: str, namespace: str = "demo") -> str:
    """Get a Deployment manifest (read-only)."""
    return get_tools().get_deployment(namespace, name)


@mcp.tool()
def get_configmap(name: str, namespace: str = "demo") -> str:
    """Get a ConfigMap with secret-like keys redacted."""
    return get_tools().get_configmap(namespace, name)


@mcp.tool()
def get_service_endpoints(name: str, namespace: str = "demo") -> str:
    """Get a Service and its Endpoints (read-only)."""
    return get_tools().get_service_endpoints(namespace, name)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
