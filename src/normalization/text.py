import hashlib
import re

_PUNCTUATION_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    lowered = text.lower()
    without_punctuation = _PUNCTUATION_RE.sub(" ", lowered)
    return _WHITESPACE_RE.sub(" ", without_punctuation).strip()


def compute_content_hash(title: str, text: str) -> str:
    combined = f"{normalize_text(title)} {normalize_text(text)}"
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:32]
