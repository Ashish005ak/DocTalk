from __future__ import annotations

import re


def replace_jargon(
    text: str,
    jargon_map: dict[str, str],
) -> tuple[str, list[str]]:
    """Replace medical jargon with plain-language equivalents.

    Performs case-insensitive whole-word replacement using word boundaries.
    Keys are processed longest-first to prevent partial matches when one
    term is a substring of another.

    Returns (cleaned_text, list_of_replaced_terms).
    """
    if not text or not jargon_map:
        return text, []

    replaced: list[str] = []
    result = text

    for term in sorted(jargon_map, key=len, reverse=True):
        pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
        if pattern.search(result):
            result = pattern.sub(jargon_map[term], result)
            replaced.append(term)

    return result, replaced
