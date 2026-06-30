"""Groq signal parser tests.

Expected: the parser accepts the required JSON schema when the provider returns
clean JSON or common LLM formatting wrappers.
Unexpected: malformed JSON, missing fields, or out-of-range scores silently
becoming a completed signal.
"""

import pytest

from provenance_guard.signals.groq_signal_service import GroqSignalService


def test_parse_response_accepts_clean_json():
    """Clean provider JSON should parse directly into normalized float scores."""
    service = GroqSignalService(client=object())

    parsed = service._parse_response(
        """
        {
          "ai_likelihood": 0.62,
          "confidence": 0.71,
          "reasons": ["polished structure"],
          "limitations": ["text alone cannot prove authorship"]
        }
        """
    )

    assert parsed["ai_likelihood"] == 0.62
    assert parsed["confidence"] == 0.71


def test_parse_response_accepts_markdown_fenced_json():
    """A fenced JSON block should be stripped before schema validation."""
    service = GroqSignalService(client=object())

    parsed = service._parse_response(
        """
        ```json
        {
          "ai_likelihood": 0.44,
          "confidence": 0.38,
          "reasons": ["mixed signals"],
          "limitations": ["short text limits confidence"]
        }
        ```
        """
    )

    assert parsed["ai_likelihood"] == 0.44
    assert parsed["confidence"] == 0.38


def test_parse_response_accepts_wrapped_json_object():
    """Wrapper text should not fail parsing when a valid JSON object is present."""
    service = GroqSignalService(client=object())

    parsed = service._parse_response(
        """
        Here is the JSON:
        {
          "ai_likelihood": 0.81,
          "confidence": 0.66,
          "reasons": ["uniform rhetorical structure"],
          "limitations": ["semantic analysis is advisory"]
        }
        """
    )

    assert parsed["ai_likelihood"] == 0.81
    assert parsed["confidence"] == 0.66


def test_parse_response_rejects_invalid_json():
    """Invalid provider output should remain a failed Groq signal path."""
    service = GroqSignalService(client=object())

    with pytest.raises(ValueError, match="Groq response was not valid JSON"):
        service._parse_response("This is not JSON.")
