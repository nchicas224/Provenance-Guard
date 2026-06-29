"""Tests for deterministic stylometric behavior.

Expected: the signal returns bounded, explainable metrics without crashing on
small inputs. Unexpected: stylometrics making extreme authorship claims or
ignoring instability caused by short text.
"""

from provenance_guard.models import AuditContext
from provenance_guard.signals.stylometric_signal_service import StylometricSignalService
from provenance_guard.utils.text_analysis import build_text_stats, normalize_text


def test_stylometric_signal_is_bounded_and_completed():
    """Stylometrics should complete and stay within its planned 0.20-0.80 range."""
    text = normalize_text(
        "This sentence has a measured structure. Another sentence follows it. "
        "The final sentence creates enough variance for a simple test."
    )
    text_stats = build_text_stats(text, text)
    audit_context = AuditContext(
        request_id="req_123",
        audit_id="audit_123",
        creator_id="user_123",
        content_type="text",
        received_at="2026-06-29T00:00:00Z",
        status="processing",
    )

    signal = StylometricSignalService().analyze(text, text_stats, audit_context)

    assert signal.status == "completed"
    assert 0.20 <= signal.ai_likelihood <= 0.80
    assert "vocabulary_diversity" in signal.raw_output


def test_short_text_reduces_stylometric_confidence():
    """Short text should attach instability context and reduce confidence."""
    text = normalize_text("Too short.")
    text_stats = build_text_stats(text, text)
    audit_context = AuditContext(
        request_id="req_123",
        audit_id="audit_123",
        creator_id="user_123",
        content_type="text",
        received_at="2026-06-29T00:00:00Z",
        status="processing",
        caution_flags=["very_short_text"],
    )

    signal = StylometricSignalService().analyze(text, text_stats, audit_context)

    assert signal.confidence_label == "low"
    assert "stylometric_unstable" in audit_context.caution_flags
