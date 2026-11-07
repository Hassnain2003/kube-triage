"""CLI entrypoint for a single diagnosis run."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from kube_triage.agent import TriageAgent
from kube_triage.kubectl import run_kubectl
from kube_triage.llm import DEFAULT_MODEL, GroqProvider
from kube_triage.tools import ClusterTools


def _load_dotenv() -> None:
    path = Path(".env")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Diagnose a Kubernetes namespace (read-only).")
    parser.add_argument("--namespace", default=os.environ.get("KUBE_NAMESPACE", "demo"))
    parser.add_argument("--configmap", default="orders-config")
    parser.add_argument(
        "--max-tool-calls",
        type=int,
        default=int(os.environ.get("KUBE_TRIAGE_MAX_TOOL_CALLS", "16")),
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get("KUBE_TRIAGE_TIMEOUT_SECONDS", "180")),
    )
    parser.add_argument("--model", default=os.environ.get("GROQ_MODEL", DEFAULT_MODEL))
    parser.add_argument("--output", default="-")
    return parser


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = build_parser().parse_args(argv)
    kubeconfig = os.environ.get("KUBECONFIG")

    def runner(kubectl_args: list[str]) -> str:
        return run_kubectl(kubectl_args, kubeconfig=kubeconfig)

    tools = ClusterTools(runner)
    llm = GroqProvider(model=args.model)
    agent = TriageAgent(
        tools,
        llm,
        max_tool_calls=args.max_tool_calls,
        timeout_seconds=args.timeout,
    )
    report = agent.run(namespace=args.namespace, configmap_name=args.configmap)
    payload = report.model_dump()
    text = json.dumps(payload, indent=2)
    if args.output == "-":
        print(text)
    else:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
