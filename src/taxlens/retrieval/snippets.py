"""Verbatim excerpts and lexical support checks over source passages."""

import re

from taxlens.retrieval.search import keyword_terms
from taxlens.retrieval.text import fold_vietnamese

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;:])\s+|\n+")


def folded_words(text: str) -> set[str]:
    """Distinct words without diacritics, so OCR text that lost accents still compares."""

    return {
        word for word in re.findall(r"\w+", fold_vietnamese(text).casefold()) if len(word) > 1
    }


def build_excerpt(content: str, query: str, maximum_length: int = 300) -> str:
    """Return the passage text that best matches the query, quoted verbatim.

    Sentences are scored by how many distinct query terms they contain (ignoring
    diacritics); the best sentence is extended with its neighbours up to the length limit.
    """

    normalized = re.sub(r"[ \t]+", " ", content).strip()
    if len(normalized) <= maximum_length:
        return " ".join(normalized.split())

    terms = {fold_vietnamese(term).casefold() for term in keyword_terms(query)}
    sentences = [sentence.strip() for sentence in _SENTENCE_BOUNDARY.split(normalized)]
    sentences = [sentence for sentence in sentences if sentence]
    if not sentences:
        return _truncate(" ".join(normalized.split()), maximum_length)
    scores = [len(terms & folded_words(sentence)) for sentence in sentences]
    best = max(range(len(sentences)), key=lambda index: (scores[index], -index))
    start, end = best, best + 1
    excerpt = sentences[best]
    while end < len(sentences) and len(excerpt) + len(sentences[end]) + 1 <= maximum_length:
        excerpt = f"{excerpt} {sentences[end]}"
        end += 1
    while start > 0 and len(excerpt) + len(sentences[start - 1]) + 1 <= maximum_length:
        start -= 1
        excerpt = f"{sentences[start]} {excerpt}"
    excerpt = " ".join(excerpt.split())
    prefix = "… " if start > 0 else ""
    suffix = " …" if end < len(sentences) else ""
    return prefix + _truncate(excerpt, maximum_length) + suffix


def lexical_support(statement: str, passage: str) -> float:
    """Share of a statement's words that occur in the passage (0.0 to 1.0)."""

    statement_words = folded_words(statement)
    if not statement_words:
        return 0.0
    return len(statement_words & folded_words(passage)) / len(statement_words)


def _truncate(text: str, maximum_length: int) -> str:
    if len(text) <= maximum_length:
        return text
    return text[: maximum_length - 1].rsplit(" ", 1)[0] + "…"
