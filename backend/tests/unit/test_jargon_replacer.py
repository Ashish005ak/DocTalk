from backend.safety.jargon_replacer import replace_jargon


def test_single_replacement():
    text, replaced = replace_jargon("dyspnea", {"dyspnea": "difficulty breathing"})
    assert text == "difficulty breathing"
    assert replaced == ["dyspnea"]


def test_multiple_replacements():
    jmap = {"dyspnea": "difficulty breathing", "myalgia": "muscle aches"}
    text, replaced = replace_jargon("dyspnea and myalgia", jmap)
    assert text == "difficulty breathing and muscle aches"
    assert set(replaced) == {"dyspnea", "myalgia"}


def test_case_insensitive():
    text, replaced = replace_jargon("Dyspnea", {"dyspnea": "difficulty breathing"})
    assert text == "difficulty breathing"
    assert replaced == ["dyspnea"]


def test_no_match_unchanged():
    original = "I have a headache"
    text, replaced = replace_jargon(original, {"dyspnea": "difficulty breathing"})
    assert text == original
    assert replaced == []


def test_empty_text():
    text, replaced = replace_jargon("", {"dyspnea": "difficulty breathing"})
    assert text == ""
    assert replaced == []


def test_empty_map():
    original = "dyspnea is present"
    text, replaced = replace_jargon(original, {})
    assert text == original
    assert replaced == []


def test_word_boundary_respected():
    text, replaced = replace_jargon(
        "dyspneatic is not dyspnea",
        {"dyspnea": "difficulty breathing"},
    )
    assert "dyspneatic" in text
    assert "difficulty breathing" in text


def test_returns_replaced_terms():
    jmap = {"tachycardia": "fast heart rate", "dyspnea": "difficulty breathing"}
    _, replaced = replace_jargon("tachycardia with dyspnea", jmap)
    assert set(replaced) == {"tachycardia", "dyspnea"}


def test_replacement_in_sentence_context():
    jmap = {"dyspnea": "difficulty breathing", "myalgia": "muscle aches"}
    text, _ = replace_jargon("You may have dyspnea and myalgia", jmap)
    assert text == "You may have difficulty breathing and muscle aches"
