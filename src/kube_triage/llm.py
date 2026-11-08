"""Small LLM provider interface. Groq is the production backend; tests inject a fake."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

DEFAULT_MODEL = "llama-3.3-70b-versatile"
FALLBACK_MODELS = ("openai/gpt-oss-120b",)


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
        api_keys: list[str] | None = None,
        model: str | None = None,
        max_retries: int = 6,
        fallback_models: tuple[str, ...] | None = None,
    ) -> None:
        from groq import Groq, RateLimitError

        self.model = model or os.environ.get("GROQ_MODEL") or DEFAULT_MODEL
        self.fallback_models = fallback_models or FALLBACK_MODELS
        self.stats = ProviderStats()
        self._max_retries = max_retries
        self._rate_limit_error = RateLimitError
        raw_keys = api_keys or os.environ.get("GROQ_API_KEYS") or os.environ.get("GROQ_API_KEY")
        if not raw_keys:
            raise RuntimeError("GROQ_API_KEYS (or GROQ_API_KEY) is not set")
        self._keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
        self._key_index = 0
        self._clients = [Groq(api_key=k) for k in self._keys]

    def _client_for_key(self, index: int):
        return self._clients[index % len(self._clients)]

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
    ) -> LLMResult:
        models = [self.model] + [m for m in self.fallback_models if m != self.model]
        last_error: Exception | None = None
        for model in models:
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": 0.0,
            }
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            # Try each API key on 429 before moving to the next model.
            for key_idx in range(len(self._keys)):
                for attempt in range(self._max_retries):
                    try:
                        self.stats.calls += 1
                        response = self._client_for_key(key_idx).chat.completions.create(**kwargs)
                        choice = response.choices[0].message.content or ""
                        usage = response.usage
                        in_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
                        out_tok = int(getattr(usage, "completion_tokens", 0) or 0)
                        self.stats.input_tokens += in_tok
                        self.stats.output_tokens += out_tok
                        self.model = model
                        self._key_index = key_idx
                        return LLMResult(text=choice, input_tokens=in_tok, output_tokens=out_tok)
                    except self._rate_limit_error as exc:
                        self.stats.retries_429 += 1
                        last_error = exc
                        time.sleep(min(32.0, 2**attempt))
                        break  # try next key instead of retrying same key
                    except Exception as exc:
                        # Groq returns 413 for TPM oversize; shrinking happens in the agent.
                        if "rate_limit" in str(exc).lower() or "413" in str(exc):
                            self.stats.retries_429 += 1
                            last_error = exc
                            time.sleep(min(32.0, 2**attempt))
                            break  # try next key
                        raise
        raise RuntimeError(
            f"Groq rate-limited on all keys/models after {self._max_retries} retries: {last_error}"
        )


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
