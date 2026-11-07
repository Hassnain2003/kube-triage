"""Small LLM provider interface. Groq is the production backend; tests inject a fake."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

DEFAULT_MODEL = "llama-3.3-70b-versatile"


@dataclass
class LLMResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ProviderStats:
    retries_429: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0


class LLMProvider(Protocol):
    stats: ProviderStats
    model: str

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
    ) -> LLMResult: ...


class GroqProvider:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        max_retries: int = 6,
    ) -> None:
        from groq import Groq, RateLimitError

        self.model = model
        self.stats = ProviderStats()
        self._max_retries = max_retries
        self._rate_limit_error = RateLimitError
        key = api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY is not set")
        self._client = Groq(api_key=key)

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
    ) -> LLMResult:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                self.stats.calls += 1
                response = self._client.chat.completions.create(**kwargs)
                choice = response.choices[0].message.content or ""
                usage = response.usage
                in_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
                out_tok = int(getattr(usage, "completion_tokens", 0) or 0)
                self.stats.input_tokens += in_tok
                self.stats.output_tokens += out_tok
                return LLMResult(text=choice, input_tokens=in_tok, output_tokens=out_tok)
            except self._rate_limit_error as exc:
                self.stats.retries_429 += 1
                last_error = exc
                time.sleep(min(32.0, 2**attempt))
        raise RuntimeError(f"Groq rate-limited after {self._max_retries} retries: {last_error}")


class FakeLLMProvider:
    """Deterministic stand-in used by unit tests. No network, no API key."""

    def __init__(self, responder: Any | None = None, model: str = "fake-llm") -> None:
        self.model = model
        self.stats = ProviderStats()
        self._responder = responder

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
    ) -> LLMResult:
        self.stats.calls += 1
        blob = "\n".join(m.get("content", "") for m in messages)
        if self._responder is not None:
            text = self._responder(messages, json_mode=json_mode)
        else:
            text = default_fake_complete(blob)
        in_tok = max(1, len(blob) // 4)
        out_tok = max(1, len(text) // 4)
        self.stats.input_tokens += in_tok
        self.stats.output_tokens += out_tok
        return LLMResult(text=text, input_tokens=in_tok, output_tokens=out_tok)


def default_fake_complete(blob: str) -> str:
    from kube_triage.untrusted import END

    stripped = blob
    # Drop untrusted blocks so injected instructions cannot drive the category.
    while "<<<UNTRUSTED_CLUSTER_DATA" in stripped:
        start = stripped.find("<<<UNTRUSTED_CLUSTER_DATA")
        end = stripped.find(END, start)
        if end < 0:
            stripped = stripped[:start]
            break
        stripped = stripped[:start] + stripped[end + len(END) :]

    category = "unknown"
    excerpt = "no matching symptom"
    tool = "list_pods"
    if "CrashLoopBackOff" in blob or "CRASH_ON_START" in blob or "invalid configuration" in blob:
        category = "crashloop_bad_config"
        excerpt = "CrashLoopBackOff"
        tool = "list_pods"
    elif "OOMKilled" in blob:
        category = "oomkilled"
        excerpt = "OOMKilled"
        tool = "describe_pod"
    elif "ImagePullBackOff" in blob or "ErrImagePull" in blob:
        category = "imagepull_wrong_tag"
        excerpt = "ImagePullBackOff"
        tool = "describe_pod"
    elif "WORKER_STUCK" in blob or "queue_length" in blob:
        category = "worker_backlog"
        excerpt = "WORKER_STUCK"
        tool = "get_logs"
    elif "redis.invalid" in blob or "wrong redis" in blob.lower():
        category = "wrong_dependency_url"
        excerpt = "REDIS_HOST: redis.invalid"
        tool = "get_configmap"
    elif "replicas: 0" in blob or "scaled to 0" in blob.lower():
        category = "readiness_dependency_down"
        excerpt = "redis replicas 0"
        tool = "get_deployment"

    if "Node: hypothesize" in blob:
        payload = {
            "root_cause_category": category,
            "rationale": f"Keyword match on {excerpt}",
            "verify_tools": [
                {
                    "name": "describe_pod",
                    "arguments": {"namespace": "demo", "name": "orders-0"},
                }
            ],
        }
        return json.dumps(payload)

    payload = {
        "root_cause_category": category,
        "explanation": f"Diagnosis from cluster evidence ({excerpt}).",
        "evidence": [
            {
                "tool": tool,
                "source_ref": f"{tool}:1",
                "excerpt": excerpt,
            }
        ],
        "suggested_fix": "Restore the last known-good ConfigMap and Deployment spec.",
        "confidence": 0.8 if category != "unknown" else 0.2,
    }
    return json.dumps(payload)
