"""Groq semantic signal service."""

import json
import os

from groq import Groq

from provenance_guard import config
from provenance_guard.models import SignalOutput


class GroqSignalService:
    """Calls Groq for a semantic attribution signal."""

    def __init__(self, api_key=None, client=None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.client = client or (Groq(api_key=self.api_key) if self.api_key else None)

    def analyze(self, normalized_text, metadata, audit_context):
        markers = self.detect_prompt_injection_markers(normalized_text)
        if markers and "prompt_injection_markers" not in audit_context.caution_flags:
            audit_context.caution_flags.append("prompt_injection_markers")

        if not self.client:
            return self._failed_signal("groq_unavailable", "GROQ_API_KEY is not configured.")

        try:
            completion = self.client.chat.completions.create(
                model=config.GROQ_MODEL,
                temperature=config.GROQ_TEMPERATURE,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": config.GROQ_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": self._user_prompt(normalized_text, metadata, markers),
                    },
                ],
            )
            content = completion.choices[0].message.content
            parsed = self._parse_response(content)
            confidence = parsed["confidence"]

            return SignalOutput(
                name="groq_semantic",
                version="v1",
                status="completed",
                ai_likelihood=parsed["ai_likelihood"],
                confidence=confidence,
                confidence_label=self._confidence_label(confidence),
                raw_output=parsed,
                explanation=self._explanation(parsed),
                error=None,
            )
        except ValueError as error:
            return self._failed_signal("groq_parse_failed", str(error))
        except Exception as error:
            return self._failed_signal(
                "groq_unavailable",
                self._safe_provider_error(error),
            )

    def detect_prompt_injection_markers(self, text):
        lowered = text.lower()
        return [marker for marker in config.PROMPT_INJECTION_MARKERS if marker in lowered]

    def _user_prompt(self, normalized_text, metadata, markers):
        return json.dumps(
            {
                "metadata": metadata or {},
                "prompt_injection_markers_detected": markers,
                "submitted_text": normalized_text,
            },
            sort_keys=True,
        )

    def _parse_response(self, content):
        parsed = self._load_json_object(content)

        required_fields = ("ai_likelihood", "confidence", "reasons", "limitations")
        missing = [field for field in required_fields if field not in parsed]
        if missing:
            raise ValueError(f"Groq response missing required fields: {', '.join(missing)}")

        ai_likelihood = parsed["ai_likelihood"]
        confidence = parsed["confidence"]
        if not isinstance(ai_likelihood, int | float) or not 0.0 <= ai_likelihood <= 1.0:
            raise ValueError("Groq ai_likelihood must be between 0.0 and 1.0.")
        if not isinstance(confidence, int | float) or not 0.0 <= confidence <= 1.0:
            raise ValueError("Groq confidence must be between 0.0 and 1.0.")
        if not isinstance(parsed["reasons"], list) or not isinstance(parsed["limitations"], list):
            raise ValueError("Groq reasons and limitations must be arrays.")

        parsed["ai_likelihood"] = float(ai_likelihood)
        parsed["confidence"] = float(confidence)
        return parsed

    def _load_json_object(self, content):
        """Load the JSON object even when the model adds common formatting noise.

        JSON mode should keep Groq responses clean, but this parser is defensive
        because providers can still return markdown fences or wrapper text during
        model drift, transient failures, or prompt-following mistakes. We only
        extract a JSON object and still validate the exact schema afterward.
        """
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Groq response was empty.")

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        cleaned = self._strip_markdown_code_fence(content)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        json_start = cleaned.find("{")
        json_end = cleaned.rfind("}")
        if json_start != -1 and json_end != -1 and json_end > json_start:
            try:
                return json.loads(cleaned[json_start : json_end + 1])
            except json.JSONDecodeError as error:
                raise ValueError("Groq response was not valid JSON.") from error

        raise ValueError("Groq response was not valid JSON.")

    def _strip_markdown_code_fence(self, content):
        """Remove a single markdown code fence around an otherwise valid JSON body."""
        cleaned = content.strip()
        if not cleaned.startswith("```"):
            return cleaned

        lines = cleaned.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()

    def _failed_signal(self, error_code, message):
        return SignalOutput(
            name="groq_semantic",
            version="v1",
            status="failed",
            ai_likelihood=None,
            confidence=None,
            confidence_label=None,
            raw_output={},
            explanation=None,
            error=f"{error_code}: {message}",
        )

    def _safe_provider_error(self, error):
        """Return provider failure context without exposing keys or prompts."""
        status_code = getattr(error, "status_code", None)
        error_type = type(error).__name__
        if status_code:
            return f"{error_type} with status {status_code}."
        return f"{error_type} during Groq semantic analysis."

    def _explanation(self, parsed):
        reasons = "; ".join(str(reason) for reason in parsed["reasons"])
        limitations = "; ".join(str(limitation) for limitation in parsed["limitations"])
        return f"Reasons: {reasons} Limitations: {limitations}"

    def _confidence_label(self, confidence):
        if confidence <= config.LOW_CONFIDENCE_MAX:
            return "low"
        if confidence <= config.MEDIUM_CONFIDENCE_MAX:
            return "medium"
        return "high"
