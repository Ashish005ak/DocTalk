from backend.safety.validator import (
    empty_response_guard,
    has_acknowledgment_opener,
    strip_banned_openings,
    strip_first_sentence,
)


def test_strip_banned_i_understand():
    result = strip_banned_openings("I understand your concern. How long?")
    assert result == "How long?"


def test_strip_banned_thank_you():
    result = strip_banned_openings("Thank you for sharing that. Tell me more.")
    assert result == "Tell me more."


def test_strip_banned_sorry():
    result = strip_banned_openings("I'm sorry to hear that. When did it start?")
    assert result == "When did it start?"


def test_no_banned_opener_unchanged():
    text = "How long has the fever lasted?"
    assert strip_banned_openings(text) == text


def test_strip_only_opener_returns_original():
    text = "I understand your concern."
    assert strip_banned_openings(text) == text


def test_case_insensitive_stripping():
    result = strip_banned_openings("i understand your concern. Next.")
    assert result == "Next."


def test_has_acknowledgment_opener_true():
    assert has_acknowledgment_opener("I understand your concerns. Rest of text.") is True


def test_has_acknowledgment_opener_false():
    assert has_acknowledgment_opener("How long has the fever lasted?") is False


def test_strip_first_sentence():
    result = strip_first_sentence("First sentence. Second sentence.")
    assert result == "Second sentence."


def test_strip_first_sentence_no_boundary():
    text = "Single fragment without ending"
    assert strip_first_sentence(text) == text


def test_empty_response_guard_empty():
    assert empty_response_guard("") == "Could you tell me more about your symptoms?"


def test_empty_response_guard_whitespace():
    assert empty_response_guard("   ") == "Could you tell me more about your symptoms?"


def test_empty_response_guard_nonempty():
    text = "Tell me about your headache."
    assert empty_response_guard(text) == text


def test_empty_response_guard_custom_fallback():
    assert empty_response_guard("", fallback="Please elaborate.") == "Please elaborate."
