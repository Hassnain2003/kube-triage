"""Typed diagnosis report produced by the agent."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ROOT_CAUSE_CATEGORIES = (
    "crashloop_bad_config",
    "oomkilled",
    "imagepull_wrong_tag",
    "readiness_dependency_down",
    "wrong_dependency_url",
    "worker_backlog",
    "unknown",
)

RootCauseCategory = Literal[
    "crashloop_bad_config",
    "oomkilled",
    "imagepull_wrong_tag",
    "readiness_dependency_down",
    "wrong_dependency_url",
    "worker_backlog",
    "unknown",
]


class EvidenceItem(BaseModel):
    """A pointer back to a tool observation, not a free-form claim."""

    tool: str
    source_ref: str
    excerpt: str = Field(min_length=1)


class DiagnosisReport(BaseModel):
    root_cause_category: RootCauseCategory
    explanation: str
    evidence: list[EvidenceItem] = Field(min_length=1)
    suggested_fix: str
    confidence: float = Field(ge=0.0, le=1.0)
    tool_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    wall_clock_seconds: float = 0.0
    retries_429: int = 0
    stopped_reason: str = "completed"


class Hypothesis(BaseModel):
    root_cause_category: RootCauseCategory
    rationale: str
    verify_tools: list[dict] = Field(default_factory=list)
