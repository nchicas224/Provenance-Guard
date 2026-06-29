"""Tests for confidence scoring safety behavior.

Expected: the scorer separates AI likelihood from final confidence and prefers
uncertainty when evidence is weak, short, degraded, or conflicting. Unexpected:
low-confidence likely_ai labels or high-confidence decisions from degraded data.
"""

from provenance_guard.models import AuditContext, SignalOutput, TextStats
from provenance_guard.scoring.confidence_scorer import ConfidenceScorer


def _signal(name, ai_likelihood, confidence):
    return SignalOutput(
        name=name,
        version="v1",
        status="completed",
        ai_likelihood=ai_likelihood,
        confidence=confidence,
        confidence_label="high" if confidence >= 0.75 else "medium",
        raw_output={},
        explanation="test signal",
        error=None,
    )


def _text_stats(character_count=500):
    return TextStats(
        character_count=character_count,
        word_count=90,
        sentence_count=5,
        estimated_reading_seconds=27,
        normalized_character_count=character_count,
    )


def _audit_context():
    return AuditContext(
        request_id="req_123",
        audit_id="audit_123",
        creator_id="user_123",
        content_type="text",
        received_at="2026-06-29T00:00:00Z",
        status="processing",
    )


def test_uncertain_result_stays_low_confidence():
    """Middle AI likelihood should be inconclusive, not medium/high confidence."""
    decision = ConfidenceScorer().score(
        audit_context=_audit_context(),
        signals=[
            _signal("groq_semantic", 0.60, 0.80),
            _signal("stylometric", 0.45, 0.80),
        ],
        text_stats=_text_stats(),
    )

    assert decision.attribution_result == "uncertain"
    assert decision.confidence_level == "low"


def test_short_text_caps_likely_ai_to_medium_when_signals_are_strong():
    """Strong aligned signals can classify short text, but not with high confidence."""
    audit_context = _audit_context()
    audit_context.caution_flags.append("short_text")

    decision = ConfidenceScorer().score(
        audit_context=audit_context,
        signals=[
            _signal("groq_semantic", 0.95, 0.90),
            _signal("stylometric", 0.80, 0.90),
        ],
        text_stats=_text_stats(character_count=120),
    )

    assert decision.confidence_level == "medium"
    assert decision.attribution_result == "likely_ai"


def test_failed_groq_caps_confidence_at_medium():
    """A degraded one-signal path may classify, but it cannot be high confidence."""
    failed_groq = SignalOutput(
        name="groq_semantic",
        version="v1",
        status="failed",
        ai_likelihood=None,
        confidence=None,
        confidence_label=None,
        raw_output={},
        explanation=None,
        error="groq_unavailable",
    )

    decision = ConfidenceScorer().score(
        audit_context=_audit_context(),
        signals=[failed_groq, _signal("stylometric", 0.80, 0.95)],
        text_stats=_text_stats(),
    )

    assert decision.degraded is True
    assert decision.confidence_level != "high"
