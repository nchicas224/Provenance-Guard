"""Stylometric signal service."""

from statistics import variance

from provenance_guard import config
from provenance_guard.models import SignalOutput
from provenance_guard.utils.text_analysis import split_sentences, tokenize_words


class StylometricSignalService:
    """Computes deterministic stylometric heuristics."""

    CONJUNCTIONS = {
        "and",
        "but",
        "or",
        "because",
        "although",
        "while",
        "since",
        "however",
    }
    PUNCTUATION = set(".,;:!?-()\"'")

    def analyze(self, normalized_text, text_stats, audit_context):
        try:
            words = tokenize_words(normalized_text)
            sentences = split_sentences(normalized_text)
            sentence_word_counts = [len(tokenize_words(sentence)) for sentence in sentences]
            complexity_scores = [
                self._sentence_complexity(sentence) for sentence in sentences
            ]

            raw_output = {
                "word_count": len(words),
                "sentence_count": len(sentences),
                "vocabulary_diversity": self._vocabulary_diversity(words),
                "sentence_length_variance": self._safe_variance(sentence_word_counts),
                "punctuation_density": self._punctuation_density(normalized_text),
                "average_sentence_complexity": self._average(complexity_scores),
                "complexity_variance": self._safe_variance(complexity_scores),
            }

            ai_likelihood = self._normalize_ai_likelihood(raw_output)
            confidence = self._confidence(text_stats, audit_context)

            return SignalOutput(
                name="stylometric",
                version="v1",
                status="completed",
                ai_likelihood=ai_likelihood,
                confidence=confidence,
                confidence_label=self._confidence_label(confidence),
                raw_output=raw_output,
                explanation=self._explanation(raw_output),
                error=None,
            )
        except Exception as error:
            return SignalOutput(
                name="stylometric",
                version="v1",
                status="failed",
                ai_likelihood=None,
                confidence=None,
                confidence_label=None,
                raw_output={},
                explanation=None,
                error=str(error),
            )

    def _vocabulary_diversity(self, words):
        if not words:
            return 0.0
        return len(set(words)) / len(words)

    def _safe_variance(self, values):
        if len(values) < 2:
            return 0.0
        return variance(values)

    def _punctuation_density(self, text):
        if not text:
            return 0.0
        punctuation_count = sum(1 for character in text if character in self.PUNCTUATION)
        return punctuation_count / len(text)

    def _sentence_complexity(self, sentence):
        words = tokenize_words(sentence)
        comma_count = sentence.count(",")
        conjunction_count = sum(1 for word in words if word in self.CONJUNCTIONS)

        # This is a bounded v1 heuristic, not a linguistic truth. Word count
        # captures length, commas approximate phrase layering, and conjunctions
        # approximate relationship structure. The normalization bound turns the
        # raw score into a 0.0-1.0 value so long sentences cannot dominate.
        raw_complexity = len(words) + (comma_count * 2) + (conjunction_count * 3)
        return min(raw_complexity / config.COMPLEXITY_NORMALIZATION_BOUND, 1.0)

    def _average(self, values):
        if not values:
            return 0.0
        return sum(values) / len(values)

    def _normalize_ai_likelihood(self, raw_output):
        # Start neutral and apply small nudges only when a metric leaves its
        # broad neutral zone. These thresholds are provisional v1 heuristics:
        # multiple weak structural signals must stack before stylometrics moves
        # meaningfully, and the final clamp prevents extreme claims.
        score = 0.50

        if raw_output["vocabulary_diversity"] < config.VOCAB_DIVERSITY_LOW:
            score += config.VOCAB_DIVERSITY_AI_NUDGE
        elif raw_output["vocabulary_diversity"] > config.VOCAB_DIVERSITY_HIGH:
            score -= config.VOCAB_DIVERSITY_HUMAN_NUDGE

        if raw_output["sentence_length_variance"] < config.SENTENCE_LENGTH_VARIANCE_LOW:
            score += config.SENTENCE_LENGTH_VARIANCE_AI_NUDGE
        elif raw_output["sentence_length_variance"] > config.SENTENCE_LENGTH_VARIANCE_HIGH:
            score -= config.SENTENCE_LENGTH_VARIANCE_HUMAN_NUDGE

        if raw_output["punctuation_density"] < config.PUNCTUATION_DENSITY_LOW:
            score += config.PUNCTUATION_DENSITY_LOW_AI_NUDGE
        elif raw_output["punctuation_density"] > config.PUNCTUATION_DENSITY_HIGH:
            score += config.PUNCTUATION_DENSITY_HIGH_AI_NUDGE

        if raw_output["complexity_variance"] < config.COMPLEXITY_VARIANCE_LOW:
            score += config.COMPLEXITY_VARIANCE_AI_NUDGE
        elif raw_output["complexity_variance"] > config.COMPLEXITY_VARIANCE_HIGH:
            score -= config.COMPLEXITY_VARIANCE_HUMAN_NUDGE

        return self._clamp(
            score,
            config.STYLOMETRIC_MIN_AI_LIKELIHOOD,
            config.STYLOMETRIC_MAX_AI_LIKELIHOOD,
        )

    def _confidence(self, text_stats, audit_context):
        # Stylometric confidence starts moderate because the signal is
        # explainable but limited. It decreases when there are too few words or
        # sentences for stable metrics, especially for short submissions.
        confidence = config.STYLOMETRIC_BASE_CONFIDENCE

        if text_stats.word_count < config.MIN_WORDS_FOR_STABLE_DIVERSITY:
            confidence -= config.STYLOMETRIC_LOW_WORD_COUNT_PENALTY
            if "stylometric_unstable" not in audit_context.caution_flags:
                audit_context.caution_flags.append("stylometric_unstable")

        if text_stats.sentence_count < config.MIN_SENTENCES_FOR_STABLE_VARIANCE:
            confidence -= config.STYLOMETRIC_LOW_SENTENCE_COUNT_PENALTY
            if "stylometric_unstable" not in audit_context.caution_flags:
                audit_context.caution_flags.append("stylometric_unstable")

        if "short_text" in audit_context.caution_flags:
            confidence -= config.STYLOMETRIC_SHORT_TEXT_PENALTY
        if "very_short_text" in audit_context.caution_flags:
            confidence -= config.STYLOMETRIC_VERY_SHORT_TEXT_PENALTY

        return self._clamp(confidence, 0.0, 1.0)

    def _confidence_label(self, confidence):
        if confidence <= config.LOW_CONFIDENCE_MAX:
            return "low"
        if confidence <= config.MEDIUM_CONFIDENCE_MAX:
            return "medium"
        return "high"

    def _explanation(self, raw_output):
        return (
            "The stylometric signal measured vocabulary diversity, sentence length "
            "variance, punctuation density, and sentence complexity."
        )

    def _clamp(self, value, minimum, maximum):
        return max(minimum, min(value, maximum))
