from backend.safety.dedup_checker import extract_question_sentences, is_duplicate_question


def test_extract_single_question():
    assert extract_question_sentences("How are you?") == ["How are you?"]


def test_extract_multiple_mixed():
    result = extract_question_sentences("Statement. Question? Another.")
    assert result == ["Question?"]


def test_extract_no_questions():
    assert extract_question_sentences("Just a statement.") == []


def test_duplicate_detected():
    response = "How long have you had the fever?"
    asked = ["How long have you had the fever?"]
    assert is_duplicate_question(response, asked) is True


def test_no_duplicate_different_questions():
    response = "Where is the pain located?"
    asked = ["How long have you had the fever?"]
    assert is_duplicate_question(response, asked) is False


def test_empty_questions_asked():
    assert is_duplicate_question("Any question here?", []) is False


def test_threshold_boundary():
    response = "How long has the headache lasted?"
    asked = ["How long has the fever lasted?"]
    assert is_duplicate_question(response, asked, threshold=0.9) is False
    assert is_duplicate_question(response, asked, threshold=0.5) is True


def test_exact_duplicate():
    q = "When did the symptoms start?"
    assert is_duplicate_question(q, [q]) is True


def test_partial_overlap_below_threshold():
    response = "Do you have any allergies?"
    asked = ["What medications are you taking?"]
    assert is_duplicate_question(response, asked) is False
