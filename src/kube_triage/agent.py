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

Allowed root_cause_category values and how to recognize them:
- crashloop_bad_config: pod in CrashLoopBackOff / BackOff restart loop, or
  CRASH_ON_START env set, or connection refused on liveness probe with
  RestartCount > 0. The container keeps dying on startup.
- oomkilled: pod status OOMKilled, or container terminated with OOMKilled
  reason, or memory limit far too low.
- imagepull_wrong_tag: ImagePullBackOff or ErrImagePull, wrong image tag,
  image not found.
- readiness_dependency_down: pod is Running but not Ready (0/1), readiness
  probe returns 503 or connection refused, dependency deployment (e.g.
  redis) has replicas: 0 or is ScaledDown, dependency endpoints are empty.
- wrong_dependency_url: ConfigMap has REDIS_HOST pointing to a
  non-existent host (e.g. redis.invalid), or app logs show connection
  refused to the dependency host.
- worker_backlog: WORKER_STUCK=1 set, worker logs show stuck/slow
  consumption, queue_length growing, API timeouts on /orders while orders
  pod itself is healthy (Running, Ready).
- unknown: no clear signal matches any category above.

Disambiguation decision tree (apply in order):
1. Is a pod CrashLoopBackOff / BackOff with RestartCount > 0? → crashloop_bad_config
   (stop here).
2. Is any pod OOMKilled? → oomkilled.
3. Is there ImagePullBackOff / ErrImagePull? → imagepull_wrong_tag.
4. Is a dependency deployment (e.g. redis) at replicas: 0 or ScaledDown, AND the app
   pod Running but not Ready (0/1)? → readiness_dependency_down.
5. Is ConfigMap REDIS_HOST pointing to a non-existent host, or do app logs show
   connection refused to that host? → wrong_dependency_url.
6. Is WORKER_STUCK=1 set with growing queue_length and API timeouts, while orders pod
   is healthy? → worker_backlog.
7. Otherwise → unknown.

Important: a Running-but-not-Ready pod with replicas: 0 dependency is
readiness_dependency_down, NOT crashloop_bad_config, even if stale CrashLoopBackOff
events exist from earlier.

Required evidence per category (cite these in your report):
- crashloop_bad_config: pod in CrashLoopBackOff / BackOff, restart count > 0
- oomkilled: OOMKilled status or memory limit too low
- imagepull_wrong_tag: ImagePullBackOff / ErrImagePull, wrong image tag
- readiness_dependency_down: app pod 0/1 Ready, dependency deployment replicas: 0
  or ScaledDown, dependency endpoints empty.
- wrong_dependency_url: ConfigMap REDIS_HOST points to non-existent host, or app
  logs show connection refused to that host.
- worker_backlog: WORKER_STUCK=1, queue_length growing, API timeouts, worker logs
  show stuck consumption.

{UNTRUSTED_HANDLING_RULES}

Output must be valid JSON matching the schema you are given. Do not wrap it in markdown.
"""

REPORT_JSON_HINT = """{
  "root_cause_category": "crashloop_bad_config",
  "explanation": "short explanation",
  "evidence": [{"tool": "list_pods", "source_ref": "list_pods:1", "excerpt": "CrashLoopBackOff"}],
  "suggested_fix": "text or unified diff",
  "confidence": 0.0
}"""

_HINTS = (
    "CrashLoopBackOff",
    "OOMKilled",
    "ImagePullBackOff",
    "ErrImagePull",
    "CRASH_ON_START",
    "WORKER_STUCK",
    "redis.invalid",
    "replicas: 0",
    "BackOff",
    "ALLOCATE_MB",
    "REDIS_HOST",
    "unhealthy",
    "timeout",
    "queue_length",
    "503",
    "ScalingReplicaSet",
    "unavailable",
)


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
        max_tool_calls: int = 24,
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
        except (BudgetExceeded, AgentTimeout) as exc:
            return self._failure_report(str(exc), getattr(exc, "reason", type(exc).__name__))
        payload = final.get("report") or {}
        try:
            report = DiagnosisReport.model_validate(payload)
        except Exception:  # noqa: BLE001
            # One retry: re-run the report node with a stricter schema reminder.
            retry_state = dict(final)
            retry_user = (
                "Node: report (retry).\n"
                "Your previous output failed schema validation. Produce valid JSON ONLY "
                "with keys: root_cause_category, explanation, evidence, suggested_fix, "
                "confidence. root_cause_category must be one of: crashloop_bad_config, "
                "oomkilled, imagepull_wrong_tag, readiness_dependency_down, "
                "wrong_dependency_url, worker_backlog, unknown. evidence must be a list "
                "of {tool, source_ref, excerpt}. suggested_fix must be text or a unified "
                "diff. confidence must be 0.0 to 1.0. Do not wrap in markdown.\n"
                f"Hypothesis: {json.dumps(retry_state.get('hypothesis') or {})}\n\n"
                + "\n\n".join(retry_state.get("evidence_blocks", []))
            )
            result = self.llm.complete(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": retry_user},
                ],
                json_mode=True,
            )
            try:
                data = _parse_json(result.text)
            except Exception:  # noqa: BLE001
                data = {
                    "root_cause_category": "unknown",
                    "rationale": "parse error",
                    "verify_tools": [],
                }
            if not data.get("evidence"):
                data["evidence"] = retry_state.get("evidence_items") or [
                    {"tool": "list_pods", "source_ref": "list_pods:1", "excerpt": "no evidence"}
                ]
            try:
                report = DiagnosisReport.model_validate(data)
            except Exception as exc2:  # noqa: BLE001
                return self._failure_report(
                    f"invalid report schema (retry failed): {exc2}", "invalid_schema"
                )
                return self._failure_report(
                    f"invalid report schema (retry failed): {exc2}", "invalid_schema"
                )
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
        return wrap_untrusted(tool, compact_cluster_text(raw))

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
        state["last_list_pods"] = list_out
        self._run_tool("get_events", {"namespace": ns}, state)
        for deploy in state.get("deployments", []):
            if len(self.tools.calls) >= self.max_tool_calls:
                break
            raw = self._run_tool("get_deployment", {"namespace": ns, "name": deploy}, state)
            excerpt = strip_deployment_yaml(raw)[:300]
            state.setdefault("evidence_items", []).append(
                {
                    "tool": "get_deployment",
                    "source_ref": f"get_deployment:{len(self.tools.calls)}",
                    "excerpt": excerpt,
                }
            )
        self._run_tool(
            "get_configmap",
            {"namespace": ns, "name": state["configmap_name"]},
            state,
        )
        for svc in state.get("services", []):
            if len(self.tools.calls) >= self.max_tool_calls:
                break
            self._run_tool("get_service_endpoints", {"namespace": ns, "name": svc}, state)
        pods = parse_pod_names(list_out)
        ordered = _pods_by_priority(list_out, pods)
        # Leave room for the verify node's tool calls.
        for pod in ordered:
            if len(self.tools.calls) >= self.max_tool_calls - 5:
                break
            try:
                previous = parse_pod_statuses(list_out).get(pod) != "Running"
                self._run_tool(
                    "get_logs",
                    {"namespace": ns, "name": pod, "tail": 40, "previous": previous},
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
        category = (state.get("hypothesis") or {}).get("root_cause_category", "unknown")
        ns = state["namespace"]

        # Targeted verification per category: collect the exact signals needed
        # to confirm or reject each hypothesis.
        targeted: list[tuple[str, dict[str, Any]]] = []
        if category == "readiness_dependency_down":
            targeted = [
                ("get_deployment", {"name": "redis"}),
                ("get_service_endpoints", {"name": "redis"}),
                ("get_configmap", {"name": state["configmap_name"]}),
            ]
        elif category == "wrong_dependency_url":
            targeted = [
                ("get_configmap", {"name": state["configmap_name"]}),
                ("get_deployment", {"name": "orders"}),
                ("get_service_endpoints", {"name": "redis"}),
            ]
        elif category == "worker_backlog":
            targeted = [
                ("get_deployment", {"name": "worker"}),
                ("get_configmap", {"name": state["configmap_name"]}),
                ("get_service_endpoints", {"name": "redis"}),
            ]
        elif category == "crashloop_bad_config":
            pods = parse_pod_names(state.get("last_list_pods", ""))
            for pod in pods[:2]:
                targeted.append(("get_logs", {"name": pod, "tail": 40, "previous": True}))
        elif category == "oomkilled":
            pods = parse_pod_names(state.get("last_list_pods", ""))
            for pod in pods[:2]:
                targeted.append(("describe_pod", {"name": pod}))
        elif category == "imagepull_wrong_tag":
            targeted = [("get_deployment", {"name": "orders"})]

        for name, args in targeted:
            if len(self.tools.calls) >= self.max_tool_calls - 3:
                break
            args = dict(args)
            args.setdefault("namespace", ns)
            try:
                self._run_tool(name, args, state)
            except Exception as exc:  # noqa: BLE001
                state["evidence_blocks"].append(self._observe(name, f"tool error: {exc}"))

        for item in requested[:3]:
            if len(self.tools.calls) >= self.max_tool_calls:
                state["stopped_reason"] = "max_tool_calls"
                break
            name = item.get("name")
            arguments = dict(item.get("arguments") or {})
            arguments.setdefault("namespace", ns)
            if not name:
                continue
            try:
                self._run_tool(name, arguments, state)
            except Exception as exc:  # noqa: BLE001
                state["evidence_blocks"].append(self._observe(name, f"tool error: {exc}"))
        return state

    def _report(self, state: AgentState) -> AgentState:
        if time.monotonic() - self._started > self.timeout_seconds:
            raise AgentTimeout("agent timeout exceeded")
        user = (
            "Node: report.\n"
            "Produce the final diagnosis JSON. Example shape:\n"
            f"{REPORT_JSON_HINT}\n"
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


def compact_cluster_text(raw: str, limit: int = 900) -> str:
    """Keep symptom lines and drop bulky kubectl YAML (managedFields, etc.)."""
    lines = [line for line in raw.splitlines() if line.strip()]
    hits = [line for line in lines if any(hint.lower() in line.lower() for hint in _HINTS)]
    chosen = hits[:40] if hits else [*lines[:12], *lines[-8:]]
    text = "\n".join(chosen)
    if len(text) > limit:
        return text[:limit] + "\n...[truncated]..."
    return text


def strip_deployment_yaml(raw: str) -> str:
    """Drop bulky managedFields/status/metadata from a deployment YAML for token efficiency."""
    try:
        import yaml

        parsed = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        return raw
    spec = parsed.get("spec", {}) if isinstance(parsed, dict) else {}
    template = spec.get("template", {}).get("spec", {}) if isinstance(spec, dict) else {}
    containers = template.get("containers", []) if isinstance(template, dict) else []
    clean_containers = []
    for c in containers if isinstance(containers, list) else []:
        if not isinstance(c, dict):
            continue
        clean_containers.append(
            {
                "name": c.get("name"),
                "image": c.get("image"),
                "imagePullPolicy": c.get("imagePullPolicy"),
                "env": (
                    [{"name": e.get("name"), "value": e.get("value")} for e in c.get("env", [])]
                    if isinstance(c.get("env"), list)
                    else None
                ),
                "resources": c.get("resources"),
                "ports": c.get("ports"),
                "livenessProbe": c.get("livenessProbe"),
                "readinessProbe": c.get("readinessProbe"),
            }
        )
    clean = {
        "kind": parsed.get("kind") if isinstance(parsed, dict) else None,
        "name": parsed.get("metadata", {}).get("name") if isinstance(parsed, dict) else None,
        "namespace": (
            parsed.get("metadata", {}).get("namespace") if isinstance(parsed, dict) else None
        ),
        "replicas": spec.get("replicas") if isinstance(spec, dict) else None,
        "containers": clean_containers,
    }
    import json as _json

    return _json.dumps(clean, indent=2)


def parse_pod_statuses(list_pods_output: str) -> dict[str, str]:
    """Return {pod_name: status} from `kubectl get pods -o wide` output."""
    statuses: dict[str, str] = {}
    for line in list_pods_output.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 3:
            statuses[parts[0]] = parts[2]
    return statuses


def _pods_by_priority(list_pods_output: str, names: list[str]) -> list[str]:
    """Non-running pods first: they carry crash/OOM/image symptoms in their logs."""
    statuses = parse_pod_statuses(list_pods_output)
    running = [n for n in names if statuses.get(n) == "Running"]
    others = [n for n in names if n not in running]
    return others + running


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
