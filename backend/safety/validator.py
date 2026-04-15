from __future__ import annotations
 
import re
 
_BANNED_OPENERS: list[re.Pattern[str]] = [
    re.compile(
        r"^I\s+understand\s+your\s+concerns?\b[^.!?]*[.!?]\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^I\s+understand\s+how\s+you\s+feel\b[^.!?]*[.!?]\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^I\s+understand\s+that\s+must\s+be\b[^.!?]*[.!?]\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^Thank\s+you\s+for\s+sharing\b[^.!?]*[.!?]\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^Thank\s+you\s+for\s+letting\s+me\s+know\b[^.!?]*[.!?]\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^Thank\s+you\s+for\s+telling\s+me\b[^.!?]*[.!?]\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^I\s+appreciate\s+you\s+sharing\b[^.!?]*[.!?]\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^I'?m\s+sorry\s+to\s+hear\s+that\b[^.!?]*[.!?]\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^I'?m\s+sorry\s+you'?re\s+going\s+through\b[^.!?]*[.!?]\s*",
        re.IGNORECASE,
    ),
]
 
_SENTENCE_END = re.compile(r"[.!?]\s+")
 
 
def strip_banned_openings(text: str) -> str:
    """Remove common LLM filler openings from the start of a response.
 
    If the entire text is just a banned opener with nothing after it,
    the original text is returned unchanged to avoid producing an empty string.
    """
    for pattern in _BANNED_OPENERS:
        m = pattern.match(text)
        if m:
            remainder = text[m.end():]
            if remainder.strip():
                return remainder
            return text
    return text
 
 
def has_acknowledgment_opener(text: str) -> bool:
    """Return True if the text begins with a banned acknowledgment opener."""
    return any(p.match(text) for p in _BANNED_OPENERS)
 
 
def strip_first_sentence(text: str) -> str:
    """Remove the first sentence from text.
 
    A sentence boundary is a period, exclamation mark, or question mark
    followed by whitespace. If no boundary is found, the text is returned
    unchanged.
    """
    m = _SENTENCE_END.search(text)
    if m:
        return text[m.end():]
    return text
 
 
def empty_response_guard(
    text: str,
    fallback: str = "Could you tell me more about your symptoms?",
) -> str:
    """Return *fallback* when *text* is empty or whitespace-only."""
    if not text or not text.strip():
        return fallback
    return text
 
 