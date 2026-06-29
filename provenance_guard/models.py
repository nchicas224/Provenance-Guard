"""Internal data contracts for Provenance Guard."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RequestEnvelope:
    request_id: str
    creator_id: str
    content_type: str
    content: str
    metadata: dict[str, Any]
    received_at: str


@dataclass
class AuditContext:
    request_id: str
    audit_id: str | None
    creator_id: str | None
    content_type: str | None
    received_at: str
    status: str
    caution_flags: list[str] = field(default_factory=list)
    degraded: bool = False
    degradation_reason: str | None = None


@dataclass
class TextPipelineInput:
    audit_context: AuditContext
    content: str
    metadata: dict[str, Any]


@dataclass
class TextStats:
    character_count: int
    word_count: int
    sentence_count: int
    estimated_reading_seconds: int
    normalized_character_count: int


@dataclass
class SignalOutput:
    name: str
    version: str
    status: str
    ai_likelihood: float | None
    confidence: float | None
    confidence_label: str | None
    raw_output: dict[str, Any]
    explanation: str | None
    error: str | None


@dataclass
class AttributionDecision:
    audit_id: str
    creator_id: str
    attribution_result: str
    ai_likelihood: float
    confidence_score: float
    confidence_level: str
    degraded: bool
    degradation_reason: str | None
    caution_flags: list[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    audit_context: AuditContext
    normalized_text: str
    text_stats: TextStats
    signals: list[SignalOutput]
    decision: AttributionDecision


@dataclass
class FormattedSubmitResponse:
    audit_id: str
    creator_id: str
    content_type: str
    attribution_result: str
    ai_likelihood: float
    confidence_score: float
    confidence_level: str
    transparency_label: str
    appeal_guidance: str | None
    signals: list[dict[str, Any]]
    degraded: bool


@dataclass
class AppealRecord:
    appeal_id: str
    audit_id: str
    creator_id: str
    original_attribution_result: str
    original_ai_likelihood: float
    original_confidence_score: float
    original_confidence_level: str
    original_transparency_label: str
    reason: str
    status: str
    created_at: str
    updated_at: str
    contact_email: str | None = None
    reviewer_notes: str | None = None
    resolution: str | None = None


@dataclass
class RequestLogRecord:
    request_id: str
    route: str
    method: str
    request_status: str
    received_at: str
    creator_id: str | None = None
    content_type: str | None = None
    status_code: int | None = None
    error_code: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    client_label: str | None = None


@dataclass
class AttributionDecisionLogRecord:
    request_id: str
    content_type: str
    decision: AttributionDecision
    transparency_label: str
    appeal_guidance: str | None
    created_at: str


@dataclass
class SignalOutputLogRecord:
    signal_id: str
    audit_id: str | None
    request_id: str
    signal: SignalOutput
    created_at: str


@dataclass
class SystemEventRecord:
    event_id: str
    event_type: str
    severity: str
    message: str
    details: dict[str, Any]
    created_at: str
    request_id: str | None = None
    audit_id: str | None = None
    creator_id: str | None = None
