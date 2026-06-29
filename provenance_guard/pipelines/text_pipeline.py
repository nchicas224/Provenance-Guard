"""Text attribution pipeline."""

import re
from datetime import UTC, datetime
from uuid import uuid4

from provenance_guard import config
from provenance_guard.models import (
    PipelineResult,
    SignalOutputLogRecord,
    SystemEventRecord,
    TextStats,
)
from provenance_guard.services.errors import SubmitValidationError


class TextPipeline:
    """Runs the v1 text attribution pipeline."""

    def __init__(
        self,
        groq_signal_service,
        stylometric_signal_service,
        confidence_scorer,
        audit_logger,
    ):
        self.groq_signal_service = groq_signal_service
        self.stylometric_signal_service = stylometric_signal_service
        self.confidence_scorer = confidence_scorer
        self.audit_logger = audit_logger

    def run(self, pipeline_input):
        audit_context = pipeline_input.audit_context
        normalized_text = self._normalize(pipeline_input.content)
        self._validate_normalized_text(normalized_text)

        text_stats = self._build_text_stats(pipeline_input.content, normalized_text)
        self._add_text_caution_flags(audit_context, text_stats)

        signals = [
            self.groq_signal_service.analyze(
                normalized_text=normalized_text,
                metadata=pipeline_input.metadata,
                audit_context=audit_context,
            ),
            self.stylometric_signal_service.analyze(
                normalized_text=normalized_text,
                text_stats=text_stats,
                audit_context=audit_context,
            ),
        ]

        for signal in signals:
            self.audit_logger.log_signal_output(
                SignalOutputLogRecord(
                    signal_id=self._new_id("signal"),
                    audit_id=audit_context.audit_id,
                    request_id=audit_context.request_id,
                    signal=signal,
                    created_at=self._now(),
                )
            )
            if signal.status == "failed":
                self._log_signal_failure(audit_context, signal)

        decision = self.confidence_scorer.score(
            audit_context=audit_context,
            signals=signals,
            text_stats=text_stats,
        )

        return PipelineResult(
            audit_context=audit_context,
            normalized_text=normalized_text,
            text_stats=text_stats,
            signals=signals,
            decision=decision,
        )

    def _normalize(self, text):
        return re.sub(r"\s+", " ", text.strip())

    def _validate_normalized_text(self, normalized_text):
        if not normalized_text:
            raise SubmitValidationError(
                code="empty_content",
                message="content must not be empty.",
                status_code=400,
            )

        if len(normalized_text) > config.MAX_TEXT_CHARS:
            raise SubmitValidationError(
                code="payload_too_large",
                message=f"text submissions must be {config.MAX_TEXT_CHARS} characters or fewer.",
                status_code=413,
            )

    def _build_text_stats(self, original_text, normalized_text):
        words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", normalized_text)
        sentences = self._simple_sentence_split(normalized_text)
        word_count = len(words)
        estimated_reading_seconds = int((word_count / 200) * 60) if word_count else 0

        return TextStats(
            character_count=len(original_text),
            word_count=word_count,
            sentence_count=len(sentences),
            estimated_reading_seconds=estimated_reading_seconds,
            normalized_character_count=len(normalized_text),
        )

    def _simple_sentence_split(self, text):
        protected = text
        replacements = {
            "e.g.": "e<dot>g<dot>",
            "i.e.": "i<dot>e<dot>",
            "Mr.": "Mr<dot>",
            "Mrs.": "Mrs<dot>",
            "Ms.": "Ms<dot>",
            "Dr.": "Dr<dot>",
            "Prof.": "Prof<dot>",
            "vs.": "vs<dot>",
            "etc.": "etc<dot>",
        }
        for source, replacement in replacements.items():
            protected = protected.replace(source, replacement)

        protected = re.sub(r"(\d)\.(\d)", r"\1<dot>\2", protected)
        parts = re.split(r"(?<=[.!?])\s+", protected)
        sentences = []
        for part in parts:
            restored = part.replace("<dot>", ".").strip()
            if restored:
                sentences.append(restored)
        return sentences

    def _add_text_caution_flags(self, audit_context, text_stats):
        if text_stats.normalized_character_count < config.VERY_SHORT_TEXT_MAX_CHARS:
            audit_context.caution_flags.append("very_short_text")
        elif text_stats.normalized_character_count < config.SHORT_TEXT_MAX_CHARS:
            audit_context.caution_flags.append("short_text")

    def _log_signal_failure(self, audit_context, signal):
        event_type = f"{signal.name}_failed"
        self.audit_logger.log_system_event(
            SystemEventRecord(
                event_id=self._new_id("event"),
                request_id=audit_context.request_id,
                audit_id=audit_context.audit_id,
                creator_id=audit_context.creator_id,
                event_type=event_type,
                severity="warning",
                message=f"{signal.name} signal failed.",
                details={"error": signal.error},
                created_at=self._now(),
            )
        )

    def _now(self):
        return datetime.now(UTC).isoformat()

    def _new_id(self, prefix):
        return f"{prefix}_{uuid4().hex}"
