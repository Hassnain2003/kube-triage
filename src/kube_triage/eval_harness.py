"""Rule-based eval: inject a fault, run the agent, score, restore, repeat."""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from kube_triage.agent import TriageAgent
from kube_triage.cli import _load_dotenv
from kube_triage.kubectl import run_kubectl
from kube_triage.llm import DEFAULT_MODEL, GroqProvider
from kube_triage.report import DiagnosisReport
from kube_triage.tools import ClusterTools

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = ROOT / "eval" / "golden"
OUTPUT_DIR = ROOT / "eval" / "output"
RESULTS_MD = ROOT / "docs" / "results.md"
NS = "demo"
FAULTS = [
    "crashloop_bad_config",
    "oomkilled",
    "imagepull_wrong_tag",
    "readiness_dependency_down",
    "wrong_dependency_url",
    "worker_backlog",
]


@dataclass
class RunRecord:
    fault: str
    run: int
    correct: bool
    evidence_ok: bool
    predicted: str
    tool_calls: int
    input_tokens: int
    output_tokens: int
    wall_clock_seconds: float
    retries_429: int
    stopped_reason: str
    error: str = ""


def _make(target: str, timeout: int = 180) -> None:
    subprocess.run(
        ["make", target],
        cwd=ROOT,
        check=True,
        timeout=timeout,
    )


def _healthy(timeout: int = 180) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            out = run_kubectl(
                [
                    "get",
                    "deploy",
                    "orders",
                    "worker",
                    "redis",
                    "-n",
                    NS,
                    "-o",
                    (
                        "jsonpath={range .items[*]}"
                        "{.metadata.name}={.status.readyReplicas}/{.spec.replicas} {end}"
                    ),
                ]
            )
        except Exception:
            time.sleep(2)
            continue
        if "orders=1/1" in out and "worker=1/1" in out and "redis=1/1" in out:
            return
        time.sleep(2)
    raise RuntimeError("cluster did not become healthy in time")


def _wait_symptom(fault: str, timeout: int = 180) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pods = run_kubectl(["get", "pods", "-n", NS, "-o", "wide"])
        describe_blob = pods
        try:
            describe_blob += "\n" + run_kubectl(["get", "pods", "-n", NS, "-o", "yaml"])
        except Exception:
            pass
        if fault == "crashloop_bad_config" and "CrashLoopBackOff" in describe_blob:
            return
        if fault == "oomkilled" and "OOMKilled" in describe_blob:
            return
        if fault == "imagepull_wrong_tag" and (
            "ImagePullBackOff" in describe_blob or "ErrImagePull" in describe_blob
        ):
            return
        if fault == "readiness_dependency_down":
            ready = run_kubectl(
                [
                    "get",
                    "deploy",
                    "orders",
                    "redis",
                    "-n",
                    NS,
                    "-o",
                    ("jsonpath={range .items[*]}{.metadata.name}:{.status.readyReplicas};{end}"),
                ]
            )
            if "redis:" in ready and "redis:1" not in ready:
                return
        if fault == "wrong_dependency_url":
            cm = run_kubectl(["get", "configmap", "orders-config", "-n", NS, "-o", "yaml"])
            if "redis.invalid" in cm:
                return
        if fault == "worker_backlog":
            if "WORKER_STUCK" in describe_blob:
                return
            try:
                env = run_kubectl(["get", "deploy", "worker", "-n", NS, "-o", "yaml"])
                if "WORKER_STUCK" in env:
                    return
            except Exception:
                pass
        time.sleep(3)
    raise RuntimeError(f"symptom for {fault} did not appear")


def _score(report: DiagnosisReport, golden: dict) -> tuple[bool, bool]:
    correct = report.root_cause_category == golden["root_cause_category"]
    blob = json.dumps(report.model_dump()).lower()
    evidence_ok = all(s.lower() in blob for s in golden.get("required_evidence", []))
    return correct, evidence_ok


def _hardware() -> dict[str, str]:
    uname = subprocess.check_output(["uname", "-a"], text=True).strip()
    kind = subprocess.check_output(["kind", "version"], text=True).strip()
    kubectl = subprocess.check_output(["kubectl", "version", "--client"], text=True).strip()
    nproc = subprocess.check_output(["nproc"], text=True).strip()
    return {
        "uname": uname,
        "kind": kind,
        "kubectl": kubectl.splitlines()[0],
        "nproc": nproc,
        "date_utc": datetime.now(UTC).strftime("%Y-%m-%d"),
        "model": os.environ.get("GROQ_MODEL", DEFAULT_MODEL),
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, cwd=ROOT
        ).strip(),
    }


def _write_results(meta: dict[str, str], records: list[RunRecord]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "runs.json").write_text(
        json.dumps({"meta": meta, "runs": [asdict(r) for r in records]}, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# kube-triage eval results",
        "",
        "Numbers in this file come from `make eval` in this repository. They are not estimates.",
        "",
        "## Environment",
        "",
        f"- Date (UTC): {meta['date_utc']}",
        f"- Git commit: `{meta['git_commit']}`",
        f"- Model: `{meta['model']}`",
        f"- kind: {meta['kind']}",
        f"- kubectl: {meta['kubectl']}",
        f"- Hardware: {meta['nproc']} CPUs; `{meta['uname']}`",
        "- Command: `make eval`",
        "",
        "## Per-fault accuracy (5 runs)",
        "",
        (
            "| Fault | Correct | Evidence cited | Mean tool calls "
            "| Mean input tokens | Mean output tokens | Mean seconds | 429 retries |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    wrong: list[RunRecord] = []
    for fault in FAULTS:
        subset = [r for r in records if r.fault == fault]
        if not subset:
            continue
        correct = sum(1 for r in subset if r.correct)
        evidence = sum(1 for r in subset if r.evidence_ok)
        mean_tc = sum(r.tool_calls for r in subset) / len(subset)
        mean_it = sum(r.input_tokens for r in subset) / len(subset)
        mean_ot = sum(r.output_tokens for r in subset) / len(subset)
        mean_sec = sum(r.wall_clock_seconds for r in subset) / len(subset)
        retries = sum(r.retries_429 for r in subset)
        lines.append(
            f"| {fault} | {correct}/5 | {evidence}/5 | {mean_tc:.1f} "
            f"| {mean_it:.0f} | {mean_ot:.0f} | {mean_sec:.1f} | {retries} |"
        )
        wrong.extend(r for r in subset if not r.correct or not r.evidence_ok)
    n = len(records) or 1
    lines += [
        "",
        "## Averages across all runs",
        "",
        f"- Accuracy (category): {sum(1 for r in records if r.correct) / n:.0%}",
        f"- Evidence cited: {sum(1 for r in records if r.evidence_ok) / n:.0%}",
        f"- Mean tool calls: {sum(r.tool_calls for r in records) / n:.1f}",
        f"- Mean input tokens: {sum(r.input_tokens for r in records) / n:.0f}",
        f"- Mean output tokens: {sum(r.output_tokens for r in records) / n:.0f}",
        f"- Mean wall-clock seconds: {sum(r.wall_clock_seconds for r in records) / n:.1f}",
        f"- Total 429 retries: {sum(r.retries_429 for r in records)}",
        "",
        "## Where the agent was wrong and why",
        "",
    ]
    if not wrong:
        lines.append("No incorrect or evidence-missing runs in this eval.")
    else:
        for r in wrong:
            lines.append(
                f"- `{r.fault}` run {r.run}: predicted `{r.predicted}` "
                f"(correct={r.correct}, evidence_ok={r.evidence_ok}, "
                f"stopped={r.stopped_reason}, error={r.error or 'none'})"
            )
    lines += [
        "",
        "## Secondary LLM-as-judge column",
        "",
        "Not used. Scoring is rule-based: exact category match plus required evidence strings.",
        "",
    ]
    RESULTS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_eval(repeats: int = 5) -> int:
    _load_dotenv()
    meta = _hardware()
    records: list[RunRecord] = []
    kubeconfig = str((ROOT / ".kube" / "triage.kubeconfig").resolve())
    os.environ["KUBECONFIG"] = kubeconfig

    def runner(args: list[str]) -> str:
        return run_kubectl(args, kubeconfig=kubeconfig)

    for fault in FAULTS:
        golden = yaml.safe_load((GOLDEN_DIR / f"{fault}.yaml").read_text(encoding="utf-8"))
        for i in range(1, repeats + 1):
            _make("restore")
            _healthy()
            error = ""
            try:
                _make(f"fault-{fault}")
                _wait_symptom(fault)
                tools = ClusterTools(runner)
                llm = GroqProvider()
                agent = TriageAgent(tools, llm)
                report = agent.run()
                correct, evidence_ok = _score(report, golden)
                records.append(
                    RunRecord(
                        fault=fault,
                        run=i,
                        correct=correct,
                        evidence_ok=evidence_ok,
                        predicted=report.root_cause_category,
                        tool_calls=report.tool_calls,
                        input_tokens=report.input_tokens,
                        output_tokens=report.output_tokens,
                        wall_clock_seconds=report.wall_clock_seconds,
                        retries_429=report.retries_429,
                        stopped_reason=report.stopped_reason,
                    )
                )
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
                records.append(
                    RunRecord(
                        fault=fault,
                        run=i,
                        correct=False,
                        evidence_ok=False,
                        predicted="error",
                        tool_calls=0,
                        input_tokens=0,
                        output_tokens=0,
                        wall_clock_seconds=0.0,
                        retries_429=0,
                        stopped_reason="error",
                        error=error,
                    )
                )
            finally:
                try:
                    _make("restore")
                    _healthy()
                except Exception:
                    pass
    _write_results(meta, records)
    failed = sum(1 for r in records if not r.correct)
    return 0 if failed == 0 else 1


def main() -> int:
    return run_eval()


if __name__ == "__main__":
    raise SystemExit(main())
