import re
import unicodedata


def normalize_text(text: str | None) -> str:
    """Normalizes text for downstream matching and alignment without altering ground truth.
    
    1. Replaces None with empty string.
    2. Applies Unicode NFKC normalization.
    3. Converts Latin characters to lowercase (Devanagari characters are untouched).
    4. Collapses whitespace (spaces, tabs, newlines) into single space and strips ends.
    """
    if not text:
        return ""

    # NFKC normalizes Unicode forms (e.g. combined accents, fullwidth characters)
    normalized = unicodedata.normalize("NFKC", text)

    # Convert Latin characters to lowercase (does not modify Hindi / Devanagari)
    normalized = normalized.lower()

    # Collapse all whitespace characters into single space
    normalized = re.sub(r"\s+", " ", normalized).strip()

    return normalized

