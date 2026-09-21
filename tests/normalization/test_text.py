from src.normalization.text import compute_content_hash, normalize_text


def test_normalize_text_lowercases_and_strips_punctuation():
    assert normalize_text("Hello, World!  Foo.") == "hello world foo"


def test_normalize_text_collapses_whitespace():
    assert normalize_text("a   b\tc\nd") == "a b c d"


def test_compute_content_hash_is_deterministic():
    first = compute_content_hash("Title", "Body text")
    second = compute_content_hash("Title", "Body text")
    assert first == second


def test_compute_content_hash_differs_for_different_content():
    first = compute_content_hash("Title A", "Body text")
    second = compute_content_hash("Title B", "Body text")
    assert first != second


def test_compute_content_hash_is_case_and_punctuation_insensitive():
    first = compute_content_hash("Airbus Unveils!", "New variant.")
    second = compute_content_hash("airbus unveils", "new variant")
    assert first == second
