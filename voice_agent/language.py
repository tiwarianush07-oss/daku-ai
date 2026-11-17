"""
DAKU Indic Language Utilities
Provides BCP-47 language mappings, Indic Unicode script detection,
and script normalization for Sarvam Voice Agents.
"""

import re
from typing import Dict, Optional, Set

# Supported Indic languages and BCP-47 codes
INDIC_LANGUAGE_CODES: Dict[str, str] = {
    "hindi": "hi-IN",
    "hi": "hi-IN",
    "hi-in": "hi-IN",
    "bengali": "bn-IN",
    "bn": "bn-IN",
    "bn-in": "bn-IN",
    "tamil": "ta-IN",
    "ta": "ta-IN",
    "ta-in": "ta-IN",
    "telugu": "te-IN",
    "te": "te-IN",
    "te-in": "te-IN",
    "marathi": "mr-IN",
    "mr": "mr-IN",
    "mr-in": "mr-IN",
    "gujarati": "gu-IN",
    "gu": "gu-IN",
    "gu-in": "gu-IN",
    "kannada": "kn-IN",
    "kn": "kn-IN",
    "kn-in": "kn-IN",
    "malayalam": "ml-IN",
    "ml": "ml-IN",
    "ml-in": "ml-IN",
    "punjabi": "pa-IN",
    "pa": "pa-IN",
    "pa-in": "pa-IN",
    "odia": "od-IN",
    "or": "od-IN",
    "od-in": "od-IN",
    "english": "en-IN",
    "en": "en-IN",
    "en-in": "en-IN",
}

# Unicode ranges for major Indic scripts
SCRIPT_UNICODE_RANGES = {
    "devanagari": (0x0900, 0x097F),
    "bengali": (0x0980, 0x09FF),
    "gurmukhi": (0x0A00, 0x0A7F),
    "gujarati": (0x0A80, 0x0AFF),
    "oriya": (0x0B00, 0x0B7F),
    "tamil": (0x0B80, 0x0BFF),
    "telugu": (0x0C00, 0x0C7F),
    "kannada": (0x0C80, 0x0CFF),
    "malayalam": (0x0D00, 0x0D7F),
}


def normalize_language_code(code_or_name: Optional[str]) -> str:
    """
    Normalizes language string or alias to standard BCP-47 (e.g. 'hindi' -> 'hi-IN').
    Defaults to 'hi-IN' if unrecognized.
    """
    if not code_or_name:
        return "hi-IN"

    clean = str(code_or_name).strip().lower().replace("_", "-")
    return INDIC_LANGUAGE_CODES.get(clean, clean if "-" in clean else "hi-IN")


def contains_indic_script(text: str) -> bool:
    """
    Returns True if the text contains any native Indic script characters.
    """
    if not text:
        return False
    for ch in text:
        cp = ord(ch)
        for _, (start, end) in SCRIPT_UNICODE_RANGES.items():
            if start <= cp <= end:
                return True
    return False


def detect_primary_script(text: str) -> str:
    """
    Detects the dominant script in the given text.
    Returns script name (e.g. 'devanagari', 'latin', 'bengali').
    """
    if not text:
        return "latin"

    counts: Dict[str, int] = {"latin": 0}
    for script in SCRIPT_UNICODE_RANGES:
        counts[script] = 0

    for ch in text:
        cp = ord(ch)
        matched = False
        for script, (start, end) in SCRIPT_UNICODE_RANGES.items():
            if start <= cp <= end:
                counts[script] += 1
                matched = True
                break
        if not matched and ch.isalpha():
            counts["latin"] += 1

    return max(counts, key=counts.get)
