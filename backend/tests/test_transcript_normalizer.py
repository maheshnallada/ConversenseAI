import pytest
from app.reconstruction.normalizer import normalize_text


def test_normalize_english_text():
    raw = "  Hello!   How can I HELP   you today?  "
    normalized = normalize_text(raw)
    assert normalized == "hello! how can i help you today?"


def test_normalize_devanagari_hindi():
    raw = "हाँ,  मैं   बात कर रहा हूँ। "
    normalized = normalize_text(raw)
    # NFKC normalizes and trims spaces; Devanagari is not corrupted or lowercased
    assert normalized == "हाँ, मैं बात कर रहा हूँ।"
    assert "हाँ" in normalized
    assert "बात" in normalized


def test_normalize_mixed_hinglish():
    raw = "Meri Policy ka renewal DATE kya hai?   "
    normalized = normalize_text(raw)
    assert normalized == "meri policy ka renewal date kya hai?"


def test_normalize_empty_and_whitespace():
    assert normalize_text("") == ""
    assert normalize_text("   \n\t  ") == ""
    assert normalize_text(None) == ""


def test_preserves_raw_text_immutably():
    raw = "  Original Text  WITH Caps &   Spaces  "
    normalized = normalize_text(raw)
    assert raw == "  Original Text  WITH Caps &   Spaces  "
    assert normalized == "original text with caps & spaces"

