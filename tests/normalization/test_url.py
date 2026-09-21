from src.normalization.url import canonicalize_url


def test_canonicalize_url_lowercases_host():
    assert canonicalize_url("https://Example.COM/Article") == "https://example.com/Article"


def test_canonicalize_url_forces_https_scheme():
    assert canonicalize_url("http://example.com/a") == "https://example.com/a"


def test_canonicalize_url_strips_tracking_params():
    result = canonicalize_url("https://example.com/a?utm_source=x&utm_medium=y&b=2")
    assert result == "https://example.com/a?b=2"


def test_canonicalize_url_strips_fragment():
    assert canonicalize_url("https://example.com/a#section") == "https://example.com/a"


def test_canonicalize_url_strips_trailing_slash():
    assert canonicalize_url("https://example.com/a/") == "https://example.com/a"


def test_canonicalize_url_preserves_root_path():
    assert canonicalize_url("https://example.com/") == "https://example.com/"


def test_canonicalize_url_preserves_non_tracking_query_params():
    result = canonicalize_url("https://example.com/a?id=42")
    assert result == "https://example.com/a?id=42"


def test_canonicalize_url_returns_input_unchanged_when_no_host():
    assert canonicalize_url("") == ""
    assert canonicalize_url("/relative/path") == "/relative/path"
