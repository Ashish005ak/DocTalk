from __future__ import annotations

import re

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])(?:\s+|$)")


def extract_question_sentences(text: str) -> list[str]:
    """Extract sentences that end with a question mark.

    Splits on sentence-ending punctuation followed by whitespace (or end of
    string), then keeps only those ending with ``?``.  Whitespace within
    each sentence is normalised.
    """
    if not text:
        return []

    parts = _SENTENCE_SPLIT.split(text.strip())
    questions: list[str] = []
    for part in parts:
        part = " ".join(part.split())
        if part and part.rstrip().endswith("?"):
            questions.append(part)
    return questions


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def is_duplicate_question(
    response: str,
    questions_asked: list[str],
    threshold: float = 0.6,
) -> bool:
    """Detect whether *response* contains a question already asked.

    Extracts question sentences from *response*, then computes Jaccard
    similarity (on lowercased word sets) against every entry in
    *questions_asked*.  Returns ``True`` as soon as any pair exceeds
    *threshold*.
    """
    if not questions_asked:
        return False

    new_questions = extract_question_sentences(response)
    if not new_questions:
        return False

    asked_word_sets = [set(q.lower().split()) for q in questions_asked]

    for q in new_questions:
        q_words = set(q.lower().split())
        for asked_ws in asked_word_sets:
            if _jaccard(q_words, asked_ws) >= threshold:
                return True

    return False
