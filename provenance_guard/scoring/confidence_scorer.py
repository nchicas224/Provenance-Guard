"""Confidence scoring service.

This module turns signal evidence into an advisory attribution decision. It
keeps two concepts separate:

- ai_likelihood: direction of evidence on a 0.0-1.0 scale.
- confidence_score: how strongly the system trusts the final result.

The scorer is intentionally conservative. When signals fail, disagree, or have
too little text, the scorer lowers confidence or chooses uncertainty rather
than producing an overconfident likely-AI result.
"""

from provenance_guard import config
from provenance_guard.models import AttributionDecision


class ConfidenceScorer:
    """Combines signal outputs into a final advisory attribution decision."""

    # These weights sum to 1.0 so the combined AI likelihood stays on the same
    # 0.0-1.0 scale as each signal. If one signal fails, the completed-signal
    # helpers re-normalize around the remaining signal instead of treating the
    # missing signal as a zero.
    SIGNAL_WEIGHTS = {
        "groq_semantic": config.GROQ_WEIGHT,
        "stylometric": config.STYLOMETRIC_WEIGHT,
    }

    def score(self, audit_context, signals, text_stats):
        """Return the final AttributionDecision for one text submission.

        The flow mirrors the planning document:
        1. Use completed signals only.
        2. Mark degraded mode when any signal fails.
        3. Compute direction with weighted AI likelihood.
        4. Convert direction into likely_human, uncertain, or likely_ai.
        5. Compute confidence only for non-uncertain results.
        6. Apply safety caps for degraded, short, or conflicting evidence.
        """
        completed = [signal for signal in signals if signal.status == "completed"]
        failed = [signal for signal in signals if signal.status == "failed"]

        if failed:
            audit_context.degraded = True
            audit_context.degradation_reason = self._degradation_reason(failed)

        if not completed:
            # With no usable evidence, the safest answer is low-confidence
            # uncertainty. We use 0.50 as neutral direction because neither
            # human-like nor AI-like evidence survived.
            audit_context.degraded = True
            audit_context.degradation_reason = "both_signals_failed"
            return self._decision(
                audit_context=audit_context,
                attribution_result="uncertain",
                ai_likelihood=0.50,
                confidence_score=config.LOW_CONFIDENCE_MAX,
                confidence_level="low",
            )

        combined_ai_likelihood = self._weighted_ai_likelihood(completed)
        attribution_result = self._attribution_result(combined_ai_likelihood)

        if attribution_result == "uncertain":
            # "Uncertain" means the system cannot confidently classify the
            # text. Even if the surviving signals have medium confidence, the
            # final result remains low confidence because the user-facing
            # meaning is inconclusive.
            weighted_signal_confidence = self._weighted_signal_confidence(completed)
            confidence_score = min(weighted_signal_confidence, config.LOW_CONFIDENCE_MAX)
            return self._decision(
                audit_context=audit_context,
                attribution_result="uncertain",
                ai_likelihood=combined_ai_likelihood,
                confidence_score=confidence_score,
                confidence_level="low",
            )

        confidence_score = self._confidence_score(
            attribution_result=attribution_result,
            combined_ai_likelihood=combined_ai_likelihood,
            completed_signals=completed,
        )
        confidence_score = self._apply_caps(
            confidence_score=confidence_score,
            attribution_result=attribution_result,
            audit_context=audit_context,
            completed_signals=completed,
            text_stats=text_stats,
        )
        confidence_level = self._confidence_level(confidence_score)

        if attribution_result != "uncertain" and confidence_level == "low":
            # A low-confidence non-uncertain label would be confusing and less
            # safe. If confidence falls into the low range, collapse the result
            # to uncertain.
            attribution_result = "uncertain"
            confidence_score = min(confidence_score, config.LOW_CONFIDENCE_MAX)
            confidence_level = "low"

        return self._decision(
            audit_context=audit_context,
            attribution_result=attribution_result,
            ai_likelihood=combined_ai_likelihood,
            confidence_score=confidence_score,
            confidence_level=confidence_level,
        )

    def _weighted_ai_likelihood(self, completed_signals):
        """Combine completed signal directions into one AI-likelihood score."""
        weight_total = sum(self.SIGNAL_WEIGHTS[signal.name] for signal in completed_signals)
        weighted_total = sum(
            signal.ai_likelihood * self.SIGNAL_WEIGHTS[signal.name]
            for signal in completed_signals
        )
        return weighted_total / weight_total

    def _weighted_signal_confidence(self, completed_signals):
        """Combine signal-local confidence using the same signal weights."""
        weight_total = sum(self.SIGNAL_WEIGHTS[signal.name] for signal in completed_signals)
        weighted_total = sum(
            signal.confidence * self.SIGNAL_WEIGHTS[signal.name]
            for signal in completed_signals
        )
        return weighted_total / weight_total

    def _attribution_result(self, combined_ai_likelihood):
        """Map AI likelihood into the wide-threshold result bands."""
        if combined_ai_likelihood <= config.LIKELY_HUMAN_MAX:
            return "likely_human"
        if combined_ai_likelihood >= config.LIKELY_AI_MIN:
            return "likely_ai"
        return "uncertain"

    def _confidence_score(
        self,
        attribution_result,
        combined_ai_likelihood,
        completed_signals,
    ):
        """Compute confidence for likely_human or likely_ai results.

        The three component weights sum to 1.0:
        - distance from threshold: strongest factor, because barely crossing a
          threshold should not be high confidence.
        - weighted signal confidence: whether the signals trust themselves.
        - agreement factor: whether independent signals point together.
        """
        distance_confidence = self._distance_confidence(
            attribution_result,
            combined_ai_likelihood,
        )
        weighted_signal_confidence = self._weighted_signal_confidence(completed_signals)
        agreement_factor = self._agreement_factor(completed_signals)

        return self._clamp(
            (distance_confidence * config.DISTANCE_CONFIDENCE_WEIGHT)
            + (weighted_signal_confidence * config.SIGNAL_CONFIDENCE_WEIGHT)
            + (agreement_factor * config.AGREEMENT_FACTOR_WEIGHT),
            0.0,
            1.0,
        )

    def _distance_confidence(self, attribution_result, combined_ai_likelihood):
        """Measure how far the score is from the nearest decision threshold."""
        if attribution_result == "likely_ai":
            return self._clamp(
                (combined_ai_likelihood - config.LIKELY_AI_MIN)
                / (1.0 - config.LIKELY_AI_MIN),
                0.0,
                1.0,
            )

        return self._clamp(
            (config.LIKELY_HUMAN_MAX - combined_ai_likelihood)
            / config.LIKELY_HUMAN_MAX,
            0.0,
            1.0,
        )

    def _agreement_factor(self, completed_signals):
        """Return a 0.0-1.0 agreement score between completed signals."""
        if len(completed_signals) < 2:
            # One surviving signal cannot demonstrate agreement. 0.60 gives
            # partial credit so a degraded single-signal path can still return
            # useful medium-confidence results, but later caps prevent high.
            return 0.60

        signal_gap = abs(completed_signals[0].ai_likelihood - completed_signals[1].ai_likelihood)
        return self._clamp(1 - signal_gap, 0.0, 1.0)

    def _apply_caps(
        self,
        confidence_score,
        attribution_result,
        audit_context,
        completed_signals,
        text_stats,
    ):
        """Apply safety caps after the base confidence score is computed.

        Caps are intentionally separate from the base formula. The formula
        estimates confidence from evidence strength; caps enforce product and
        safety policy such as "degraded cannot be high confidence" and "short
        text should usually be uncertain/low confidence."
        """
        capped_score = confidence_score

        if audit_context.degraded:
            # If any signal failed, the system cannot claim high confidence.
            capped_score = min(capped_score, config.MEDIUM_CONFIDENCE_MAX)

        if text_stats.normalized_character_count < config.SHORT_TEXT_MAX_CHARS:
            # Short text often lacks enough evidence. Only exceptionally strong
            # and aligned signals can avoid the low-confidence cap.
            if not self._both_signals_high_confidence_and_strongly_agree(completed_signals):
                capped_score = min(capped_score, config.LOW_CONFIDENCE_MAX)

        if self._has_signal_disagreement(completed_signals):
            # Divergent signals can still be informative, but disagreement
            # prevents high-confidence labels.
            capped_score = min(capped_score, config.MEDIUM_CONFIDENCE_MAX)
            if "signal_disagreement" not in audit_context.caution_flags:
                audit_context.caution_flags.append("signal_disagreement")

        if attribution_result == "likely_ai" and self._has_major_caution_flag(audit_context):
            # likely_ai is the highest-harm false-positive path, so major
            # caution flags keep it out of the high-confidence range.
            capped_score = min(capped_score, config.MEDIUM_CONFIDENCE_MAX)

        if attribution_result == "likely_ai" and not self._high_confidence_likely_ai_allowed(
            calculated_confidence_score=capped_score,
            completed_signals=completed_signals,
            audit_context=audit_context,
        ):
            capped_score = min(capped_score, config.MEDIUM_CONFIDENCE_MAX)

        return capped_score

    def _both_signals_high_confidence_and_strongly_agree(self, completed_signals):
        """Check the narrow exception that lets short text avoid a low cap."""
        if len(completed_signals) < 2:
            return False

        return (
            all(signal.confidence >= config.HIGH_CONFIDENCE_MIN for signal in completed_signals)
            and not self._has_signal_disagreement(completed_signals)
            and self._signal_gap(completed_signals) < config.STRONG_AGREEMENT_MAX_GAP
        )

    def _high_confidence_likely_ai_allowed(
        self,
        calculated_confidence_score,
        completed_signals,
        audit_context,
    ):
        """Enforce extra requirements for high-confidence likely_ai.

        calculated_confidence_score is the final confidence score after the
        base formula and earlier caps. It is not the same as signal agreement.
        A result can cross the high-confidence threshold because it is far from
        the AI threshold or because the completed signals have high local
        confidence. This gate adds stricter likely-AI requirements before the
        system is allowed to keep a high-confidence likely_ai label.

        A likely-AI result may remain low or medium confidence with one signal
        or caution flags, but high confidence requires both signals, strong
        agreement, high weighted signal confidence, and no major caution flags.
        """
        if calculated_confidence_score < config.HIGH_CONFIDENCE_MIN:
            # The result is not high confidence, so this high-confidence gate
            # does not need to block it. Other safety caps still apply in
            # _apply_caps before this function is called.
            return True
        if len(completed_signals) < 2:
            return False
        if self._signal_gap(completed_signals) >= config.STRONG_AGREEMENT_MAX_GAP:
            return False
        if self._weighted_signal_confidence(completed_signals) < config.HIGH_CONFIDENCE_MIN:
            return False
        return not self._has_major_caution_flag(audit_context)

    def _has_signal_disagreement(self, completed_signals):
        """Detect a large AI-likelihood gap between the two signals."""
        if len(completed_signals) < 2:
            return False
        return self._signal_gap(completed_signals) > config.SIGNAL_DISAGREEMENT_THRESHOLD

    def _signal_gap(self, completed_signals):
        """Return the absolute distance between two signal directions."""
        return abs(completed_signals[0].ai_likelihood - completed_signals[1].ai_likelihood)

    def _has_major_caution_flag(self, audit_context):
        """Return True when workflow context raises false-positive risk."""
        major_flags = {
            "very_short_text",
            "short_text",
            "signal_disagreement",
            "groq_unavailable",
            "stylometric_unstable",
            "unsupported_structure",
            "possible_translation_or_formal_style",
            "prompt_injection_markers",
        }
        return any(flag in major_flags for flag in audit_context.caution_flags)

    def _degradation_reason(self, failed_signals):
        """Summarize which signal path failed for audit and label add-ons."""
        failed_names = {signal.name for signal in failed_signals}
        if failed_names == {"groq_semantic", "stylometric"}:
            return "both_signals_failed"
        if "groq_semantic" in failed_names:
            return "groq_unavailable"
        if "stylometric" in failed_names:
            return "stylometric_failed"
        return "degraded_mode"

    def _confidence_level(self, confidence_score):
        """Convert final confidence score into low, medium, or high."""
        if confidence_score <= config.LOW_CONFIDENCE_MAX:
            return "low"
        if confidence_score <= config.MEDIUM_CONFIDENCE_MAX:
            return "medium"
        return "high"

    def _decision(
        self,
        audit_context,
        attribution_result,
        ai_likelihood,
        confidence_score,
        confidence_level,
    ):
        """Build the stable AttributionDecision data contract."""
        return AttributionDecision(
            audit_id=audit_context.audit_id,
            creator_id=audit_context.creator_id,
            attribution_result=attribution_result,
            ai_likelihood=ai_likelihood,
            confidence_score=confidence_score,
            confidence_level=confidence_level,
            degraded=audit_context.degraded,
            degradation_reason=audit_context.degradation_reason,
            caution_flags=list(audit_context.caution_flags),
        )

    def _clamp(self, value, minimum, maximum):
        """Keep a score inside its intended scale."""
        return max(minimum, min(value, maximum))
