from __future__ import annotations

import kube_triage.mcp_server as server


def test_mcp_server_registers_readonly_tools() -> None:
    expected = {
        "list_pods",
        "describe_pod",
        "get_events",
        "get_logs",
        "get_deployment",
        "get_configmap",
        "get_service_endpoints",
    }
    for name in expected:
        assert callable(getattr(server, name))
    assert server.mcp is not None
    assert server.mcp.name == "kube-triage"
