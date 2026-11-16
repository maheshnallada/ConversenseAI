from typing import Literal

from pydantic import BaseModel, Field


class StagedCallSummary(BaseModel):
    folder_id: str
    display_name: str
    is_ready: bool
    validation_errors: list[str]


class StagedCallListResponse(BaseModel):
    calls: list[StagedCallSummary]


class StagedCallImportRequest(BaseModel):
    folder_ids: list[str] = Field(min_length=1)


class AudioValidationResponse(BaseModel):
    is_valid: bool
    channels: int | None = None
    sample_rate: int | None = None
    sample_width: int | None = None
    duration_s: float | None = None
    is_silent: bool = False


class CallProcessingErrorResponse(BaseModel):
    stage: Literal["timeline", "observability", "evaluation"]
    message: str


class CallProcessingSummaryResponse(BaseModel):
    transcript_turns: int
    timeline_status: Literal["ready", "failed"]
    observability_status: Literal["ready", "failed"]
    evaluation_status: Literal["ready", "failed"]
    evaluation_run_id: str | None
    errors: list[CallProcessingErrorResponse] = Field(default_factory=list)


class CallImportResultResponse(BaseModel):
    folder_name: str
    interaction_id: str | None
    status: Literal["created", "replayed", "invalid", "conflict", "failed"]
    files_count: int
    audio_validation: AudioValidationResponse
    validation_errors: list[str] = Field(default_factory=list)
    error: str | None = None
    has_agent_manifest: bool = False
    phone_answered: bool = False
    processing: CallProcessingSummaryResponse | None = None


class CallImportBatchResponse(BaseModel):
    total_calls: int
    created: int
    replayed: int
    failed: int
    calls: list[CallImportResultResponse]
