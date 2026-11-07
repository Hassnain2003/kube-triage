"""LangGraph diagnosis agent: gather_evidence -> hypothesize -> verify -> report."""

from __future__ import annotations

import json
import time
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from kube_triage.llm import LLMProvider
from kube_triage.report import DiagnosisReport, EvidenceItem, Hypothesis
from kube_triage.tools import ClusterTools, dispatch, parse_pod_names, tool_specs
from kube_triage.untrusted import UNTRUSTED_HANDLING_RULES, wrap_untrusted

SYSTEM_PROMPT = f"""You are kube-triage, a read-only Kubernetes incident analyst.

You diagnose broken deployments. You never change a cluster. You never suggest running
kubectl apply yourself as an executed action; you only return text or a unified diff
that a human can review.

Allowed root_cause_category values:
- crashloop_bad_config
- oomkilled
- imagepull_wrong_tag
- readiness_dependency_down
- wrong_dependency_url
- worker_backlog
- unknown

{UNTRUSTED_HANDLING_RULES}

Output must be valid JSON matching the schema you are given. Do not wrap it in markdown.
"""


class AgentState(TypedDict, total=False):
    namespace: str
    configmap_name: str
    deployments: list[str]
    services: list[str]
    evidence_blocks: list[str]
    evidence_items: list[dict[str, str]]
    hypothesis: dict[str, Any]
    report: dict[str, Any]
    stopped_reason: str


class BudgetExceeded(RuntimeError):
    pass


class AgentTimeout(RuntimeError):
    pass


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    return json.loads(cleaned)


class TriageAgent:
    def __init__(
        self,
        tools: ClusterTools,
        llm: LLMProvider,
        *,
        max_tool_calls: int = 16,
        timeout_seconds: float = 180.0,
    ) -> None:
        self.tools = tools
        self.llm = llm
        self.max_tool_calls = max_tool_calls
        self.timeout_seconds = timeout_seconds
        self._started = 0.0
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("gather_evidence", self._gather_evidence)
        graph.add_node("hypothesize", self._hypothesize)
        graph.add_node("verify", self._verify)
        graph.add_node("report", self._report)
        graph.add_edge(START, "gather_evidence")
        graph.add_edge("gather_evidence", "hypothesize")
        graph.add_edge("hypothesize", "verify")
        graph.add_edge("verify", "report")
        graph.add_edge("report", END)
        return graph.compile()

    def run(
        self,
        *,
        namespace: str = "demo",
        configmap_name: str = "orders-config",
        deployments: list[str] | None = None,
        services: list[str] | None = None,
    ) -> DiagnosisReport:
        self._started = time.monotonic()
        initial: AgentState = {
            "namespace": namespace,
            "configmap_name": configmap_name,
            "deployments": deployments or ["orders", "worker", "redis"],
            "services": services or ["orders", "redis"],
            "evidence_blocks": [],
            "evidence_items": [],
            "stopped_reason": "completed",
        }
        try:
            final = self._graph.invoke(initial)
        except (BudgetExceeded, AgentTimeout, json.JSONDecodeError) as exc:
            return self._failure_report(str(exc), getattr(exc, "reason", type(exc).__name__))
        payload = final.get("report") or {}
        try:
            report = DiagnosisReport.model_validate(payload)
        except Exception as exc:  # noqa: BLE001
            return self._failure_report(f"invalid report schema: {exc}", "invalid_schema")
        report.tool_calls = len(self.tools.calls)
        report.input_tokens = self.llm.stats.input_tokens
        report.output_tokens = self.llm.stats.output_tokens
        report.retries_429 = self.llm.stats.retries_429
        report.wall_clock_seconds = round(time.monotonic() - self._started, 3)
        report.stopped_reason = final.get("stopped_reason", "completed")
        return report

    def _check_limits(self) -> None:
        if time.monotonic() - self._started > self.timeout_seconds:
            raise AgentTimeout("agent timeout exceeded")
        if len(self.tools.calls) >= self.max_tool_calls:
            raise BudgetExceeded("max tool calls exceeded")

    def _observe(self, tool: str, raw: str) -> str:
        wrapped = wrap_untrusted(tool, raw)
        return wrapped

    def _run_tool(self, name: str, arguments: dict[str, Any], state: AgentState) -> str:
        self._check_limits()
        raw = dispatch(self.tools, name, arguments)
        ref = f"{name}:{len(self.tools.calls)}"
        state.setdefault("evidence_blocks", []).append(self._observe(ref, raw))
        state.setdefault("evidence_items", []).append(
            {"tool": name, "source_ref": ref, "excerpt": _excerpt(raw)}
        )
        return raw

    def _gather_evidence(self, state: AgentState) -> AgentState:
        ns = state["namespace"]
        list_out = self._run_tool("list_pods", {"namespace": ns}, state)
        self._run_tool("get_events", {"namespace": ns}, state)
        for deploy in state.get("deployments", []):
            self._run_tool("get_deployment", {"namespace": ns, "name": deploy}, state)
        self._run_tool(
            "get_configmap",
            {"namespace": ns, "name": state["configmap_name"]},
            state,
        )
        for svc in state.get("services", []):
            self._run_tool("get_service_endpoints", {"namespace": ns, "name": svc}, state)
        pods = parse_pod_names(list_out)
        for pod in pods[:5]:
            if len(self.tools.calls) >= self.max_tool_calls - 2:
                break
            try:
                self._run_tool(
                    "get_logs",
                    {"namespace": ns, "name": pod, "tail": 80, "previous": False},
                    state,
                )
            except Exception as exc:  # noqa: BLE001
                state["evidence_blocks"].append(self._observe(f"get_logs:{pod}", str(exc)))
        return state

    def _hypothesize(self, state: AgentState) -> AgentState:
        self._check_limits()
        user = (
            "Node: hypothesize.\n"
            "Read the untrusted evidence and return JSON with keys "
            "root_cause_category, rationale, verify_tools.\n"
            "verify_tools is a list of {name, arguments} using only these tools:\n"
            f"{json.dumps(tool_specs())}\n"
            "Request at most 3 verify tools. Prefer describe_pod and previous logs "
            "for crash/OOM/image issues.\n\n" + "\n\n".join(state.get("evidence_blocks", []))
        )
        result = self.llm.complete(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            json_mode=True,
        )
        data = _parse_json(result.text)
        hypothesis = Hypothesis.model_validate(
            {
                "root_cause_category": data.get("root_cause_category", "unknown"),
                "rationale": data.get("rationale", ""),
                "verify_tools": data.get("verify_tools") or [],
            }
        )
        state["hypothesis"] = hypothesis.model_dump()
        return state

    def _verify(self, state: AgentState) -> AgentState:
        requested = list((state.get("hypothesis") or {}).get("verify_tools") or [])
        for item in requested[:3]:
            if len(self.tools.calls) >= self.max_tool_calls:
                state["stopped_reason"] = "max_tool_calls"
                break
            name = item.get("name")
            arguments = dict(item.get("arguments") or {})
            arguments.setdefault("namespace", state["namespace"])
            if not name:
                continue
            try:
                self._run_tool(name, arguments, state)
            except Exception as exc:  # noqa: BLE001
                state["evidence_blocks"].append(self._observe(name, f"tool error: {exc}"))
        return state

    def _report(self, state: AgentState) -> AgentState:
        self._check_limits()
        schema = DiagnosisReport.model_json_schema()
        user = (
            "Node: report.\n"
            "Produce the final diagnosis JSON. Schema:\n"
            f"{json.dumps(schema)}\n"
            "evidence must cite tool outputs using source_ref values from the evidence.\n"
            "suggested_fix must be human-readable text or a unified diff.\n"
            "Do not claim you changed the cluster.\n"
            "When cluster data contains these tokens, copy them verbatim into evidence excerpts: "
            "CrashLoopBackOff, OOMKilled, ImagePullBackOff, ErrImagePull, CRASH_ON_START, "
            "redis.invalid, WORKER_STUCK, replicas: 0.\n"
            f"Hypothesis: {json.dumps(state.get('hypothesis') or {})}\n\n"
            + "\n\n".join(state.get("evidence_blocks", []))
        )
        result = self.llm.complete(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user},
            ],
            json_mode=True,
        )
        data = _parse_json(result.text)
        if not data.get("evidence"):
            data["evidence"] = state.get("evidence_items") or [
                {"tool": "list_pods", "source_ref": "list_pods:1", "excerpt": "no evidence"}
            ]
        state["report"] = data
        return state

    def _failure_report(self, explanation: str, reason: str) -> DiagnosisReport:
        return DiagnosisReport(
            root_cause_category="unknown",
            explanation=explanation,
            evidence=[
                EvidenceItem(
                    tool="agent",
                    source_ref="agent:error",
                    excerpt=explanation[:240],
                )
            ],
            suggested_fix="Re-run diagnosis after checking kubeconfig and step budget.",
            confidence=0.0,
            tool_calls=len(self.tools.calls),
            input_tokens=self.llm.stats.input_tokens,
            output_tokens=self.llm.stats.output_tokens,
            retries_429=self.llm.stats.retries_429,
            wall_clock_seconds=round(time.monotonic() - self._started, 3) if self._started else 0.0,
            stopped_reason=reason,
        )


def _excerpt(raw: str) -> str:
    tokens = (
        "CrashLoopBackOff",
        "OOMKilled",
        "ImagePullBackOff",
        "ErrImagePull",
        "CRASH_ON_START",
        "WORKER_STUCK",
        "redis.invalid",
        "replicas: 0",
        "BackOff",
    )
    for line in raw.splitlines():
        if any(token.lower() in line.lower() for token in tokens):
            return line.strip()[:240]
    lines = [line for line in raw.splitlines() if line.strip()]
    return (lines[-1] if lines else "(empty)")[:240]
