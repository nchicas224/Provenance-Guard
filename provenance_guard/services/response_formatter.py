"""API response formatting service."""

from datetime import UTC, datetime

from provenance_guard.models import AttributionDecisionLogRecord


class ResponseFormatter:
    """Builds the public submit response and stores the final audit decision."""

    LABELS = {
        ("likely_ai", "high"): (
            "This submission shows strong patterns that are consistent with "
            "AI-generated text. This label is based on multiple signals, but it "
            "should still be reviewed with context before any action is taken."
        ),
        ("likely_ai", "medium"): (
            "This submission shows some patterns that are consistent with "
            "AI-generated text. The result is not definitive and should be "
            "reviewed with caution."
        ),
        ("likely_human", "high"): (
            "This submission shows strong patterns that are consistent with "
            "human-written text. This label is based on multiple signals, but it "
            "should not be treated as absolute proof of authorship."
        ),
        ("likely_human", "medium"): (
            "This submission shows some patterns that are consistent with "
            "human-written text. The result is not definitive and should be "
            "reviewed with caution."
        ),
        ("uncertain", "low"): (
            "This submission could not be confidently attributed. The available "
            "signals are mixed or insufficient, so this result should be treated "
            "as inconclusive."
        ),
    }

    DEGRADED_ADD_ONS = {
        "groq_unavailable": (
            " Semantic analysis was unavailable, so this result relies more "
            "heavily on stylometric signals and has reduced confidence."
        ),
        "stylometric_failed": (
            " Stylometric analysis was unavailable, so this result relies more "
            "heavily on semantic analysis and has reduced confidence."
        ),
        "both_signals_failed": (
            " The attribution signals were unavailable, so the system could not "
            "make a reliable classification."
        ),
        "short_text": (
            " The submission is short, so there may not be enough evidence for a "
            "reliable attribution."
        ),
        "very_short_text": (
            " The submission is short, so there may not be enough evidence for a "
            "reliable attribution."
        ),
        "signal_disagreement": (
            " The analysis signals did not fully agree, so this result has "
            "reduced confidence."
        ),
    }

    APPEAL_GUIDANCE = (
        "If you believe this label is incorrect, you can submit an appeal using "
        "the audit_id returned with this result."
    )

    def __init__(self, audit_logger):
        self.audit_logger = audit_logger

    def format(self, pipeline_result):
        decision = pipeline_result.decision
        label = self._transparency_label(decision)
        appeal_guidance = (
            self.APPEAL_GUIDANCE if decision.attribution_result == "likely_ai" else None
        )

        self.audit_logger.log_attribution_decision(
            AttributionDecisionLogRecord(
                request_id=pipeline_result.audit_context.request_id,
                content_type=pipeline_result.audit_context.content_type,
                decision=decision,
                transparency_label=label,
                appeal_guidance=appeal_guidance,
                created_at=self._now(),
            )
        )

        return {
            "audit_id": decision.audit_id,
            "creator_id": decision.creator_id,
            "content_type": pipeline_result.audit_context.content_type,
            "attribution_result": decision.attribution_result,
            "ai_likelihood": decision.ai_likelihood,
            "confidence_score": decision.confidence_score,
            "confidence_level": decision.confidence_level,
            "transparency_label": label,
            "appeal_guidance": appeal_guidance,
            "signals": [self._signal_response(signal) for signal in pipeline_result.signals],
            "degraded": decision.degraded,
        }

    def _transparency_label(self, decision):
        label = self.LABELS[(decision.attribution_result, decision.confidence_level)]

        add_on_keys = []
        if decision.degradation_reason:
            add_on_keys.append(decision.degradation_reason)
        add_on_keys.extend(decision.caution_flags)

        seen = set()
        for key in add_on_keys:
            if key in seen:
                continue
            seen.add(key)
            add_on = self.DEGRADED_ADD_ONS.get(key)
            if add_on:
                label += add_on

        return label

    def _signal_response(self, signal):
        return {
            "name": signal.name,
            "status": signal.status,
            "ai_likelihood": signal.ai_likelihood,
            "confidence": signal.confidence,
            "confidence_label": signal.confidence_label,
        }

    def _now(self):
        return datetime.now(UTC).isoformat()
