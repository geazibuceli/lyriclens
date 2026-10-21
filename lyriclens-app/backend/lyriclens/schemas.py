from typing import Literal, Any
from pydantic import BaseModel, ConfigDict, Field
from .domain import Segment

State = Literal["queued", "processing", "completed", "failed", "canceled", "interrupted"]


class PipelineResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    state: Literal["completed", "failed"]
    seconds: float
    original: list[Segment] | None = None
    original_text: str | None = None
    edited: list[Segment] | None = None
    detected_language: str | None = None
    language_source: str | None = None
    warnings: list[str] | None = None
    error: str | None = None
    provenance: dict[str, Any] | None = None


class Job(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    filename: str
    title: str = Field(default="", max_length=200)
    sha256: str
    bytes: int
    state: State
    stage: str
    requested_language: str
    pipelines: list[Literal["direct", "vocals"]]
    model_id: str
    revision: str
    inference: dict[str, Any]
    environment: dict[str, Any]
    created_at: str
    cancel_requested: bool
    results: dict[str, PipelineResult]


class ModelReadiness(BaseModel):
    model_id: str
    revision: str
    prepared: bool
    separation_prepared: bool
    ffmpeg_available: bool
    languages: dict[str, str]
    max_bytes: int
    max_seconds: float
    device: str
    compute_type: str
    profiles: list[dict[str, Any]] = Field(default_factory=list)
