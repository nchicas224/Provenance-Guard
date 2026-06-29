"""Shared text normalization, tokenization, and stats helpers."""

import re

from provenance_guard import config
from provenance_guard.models import TextStats


ABBREVIATION_REPLACEMENTS = {
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


def normalize_text(text):
    return re.sub(r"\s+", " ", text.strip())


def tokenize_words(text):
    return re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text.lower())


def split_sentences(text):
    protected = text
    for source, replacement in ABBREVIATION_REPLACEMENTS.items():
        protected = protected.replace(source, replacement)

    protected = re.sub(r"(\d)\.(\d)", r"\1<dot>\2", protected)
    parts = re.split(r"(?<=[.!?])\s+", protected)
    return [part.replace("<dot>", ".").strip() for part in parts if part.strip()]


def build_text_stats(original_text, normalized_text):
    words = tokenize_words(normalized_text)
    sentences = split_sentences(normalized_text)
    word_count = len(words)
    estimated_reading_seconds = (
        int((word_count / config.READING_WORDS_PER_MINUTE) * 60)
        if word_count
        else 0
    )

    return TextStats(
        character_count=len(original_text),
        word_count=word_count,
        sentence_count=len(sentences),
        estimated_reading_seconds=estimated_reading_seconds,
        normalized_character_count=len(normalized_text),
    )
