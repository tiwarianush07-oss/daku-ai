"""
DAKU TTS Normalizer Module
Preprocesses and cleans agent responses before sending to Sarvam Bulbul v3.
Ensures:
1. Native Indic script preservation.
2. Contextual Indic transliteration (e.g. 'aapka order confirm ho gaya hai' -> 'आपका order confirm हो गया है।').
3. Preservation of English technical terms (RAM, CPU, Notepad, Chrome, Windows, PDF, GB, MB).
4. Spoken normalization of URLs and IP addresses.
5. Removal of <think> tags, JSON structures, tool metadata, and debug logs.
6. Clean, natural, spoken prosody.
"""

import re
from typing import Dict, List, Optional, Set

from voice_agent.language import contains_indic_script

# Common Hinglish phrases and their Devanagari equivalents (preserves English nouns)
HINGLISH_TO_DEVANAGARI: Dict[str, str] = {
    "aapka": "आपका",
    "aapki": "आपकी",
    "aap": "आप",
    "main": "मैं",
    "mera": "मेरा",
    "meri": "मेरी",
    "hum": "हम",
    "hai": "है",
    "hain": "हैं",
    "ho": "हो",
    "tha": "था",
    "thi": "थी",
    "the": "थे",
    "gaya": "गया",
    "gayi": "गयी",
    "gaye": "गये",
    "kar": "कर",
    "karo": "करो",
    "karein": "करें",
    "karta": "करता",
    "karti": "करती",
    "diya": "दिया",
    "diye": "दिए",
    "dijiye": "दीजिए",
    "liye": "लिए",
    "ka": "का",
    "ki": "की",
    "ke": "के",
    "ko": "को",
    "se": "से",
    "mein": "में",
    "par": "पर",
    "aur": "और",
    "ya": "या",
    "nahi": "नहीं",
    "nahin": "नहीं",
    "haan": "हाँ",
    "kya": "क्या",
    "kyun": "क्यों",
    "kaise": "कैसे",
    "kahan": "कहाँ",
    "kab": "कब",
    "kaun": "कौन",
    "theek": "ठीक",
    "shukriya": "शुक्रिया",
    "dhanyavad": "धन्यवाद",
    "namaste": "नमस्ते",
    "alvida": "अलविदा",
    "chalu": "चालू",
    "kholo": "खोलो",
    "band": "बंद",
    "madad": "मदद",
}

# Technical terms to strictly preserve in English Latin script
PRESERVED_TECH_TERMS: Set[str] = {
    "ram", "cpu", "gpu", "ssd", "hdd", "gb", "mb", "kb", "tb",
    "windows", "linux", "macos", "android", "ios",
    "chrome", "edge", "firefox", "browser", "notepad", "calculator",
    "file", "folder", "directory", "desktop", "terminal", "powershell",
    "cmd", "process", "task", "agent", "daku", "hermes", "server", "client",
    "url", "http", "https", "pdf", "txt", "api", "key", "token", "wifi",
    "bluetooth", "system", "status", "version", "online", "offline",
    "order", "confirm", "confirmed", "cancel", "cancelled", "stop", "start",
    "launch", "open", "close", "restart", "shutdown",
}


class TTSNormalizer:
    """
    Spoken text normalizer optimizing DAKU agent responses for Bulbul v3.
    """

    @classmethod
    def clean_for_speech(cls, text: str, target_lang: str = "hi-IN") -> str:
        """
        Main pipeline cleaning and normalizing text for TTS synthesis.
        """
        if not text or not text.strip():
            return ""

        output = text.strip()

        # 1. Remove <think>...</think> reasoning tags
        output = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL)

        # 2. Remove markdown code blocks and inline code
        output = re.sub(r"```.*?```", "", output, flags=re.DOTALL)
        output = re.sub(r"`([^`]+)`", r"\1", output)

        # 3. Remove raw JSON structures or tool dictionary dumps
        output = re.sub(r"\{[^{}]*\}", "", output)

        # 4. Remove system prefixes and log metadata
        output = re.sub(r"\[DAKU(?:\s*\([^)]*\))?\]:?", "", output, flags=re.IGNORECASE)
        output = re.sub(r"\[DAKU\s+Thinking\]:?", "", output, flags=re.IGNORECASE)
        output = re.sub(r"\[.*?\]", "", output)

        # 5. Normalize URLs
        output = cls._normalize_urls(output)

        # 6. Normalize IP addresses and decimal numbers
        output = cls._normalize_numbers_and_ips(output)

        # 7. Strip Markdown header tokens and list bullets
        output = re.sub(r"^#{1,6}\s*", "", output, flags=re.MULTILINE)
        output = re.sub(r"^\s*[-*+]\s+", "", output, flags=re.MULTILINE)
        output = re.sub(r"[*_~#]", "", output)

        # 8. Contextual Hinglish to Devanagari normalization for hi-IN
        if target_lang.startswith("hi") and not contains_indic_script(output):
            output = cls._normalize_hinglish_to_devanagari(output)

        # 9. Clean up whitespace and punctuation
        output = re.sub(r"\s+", " ", output).strip()

        # Ensure sentence ends with natural punctuation
        if output and not output[-1] in ".?!।":
            output += "।" if contains_indic_script(output) else "."

        return output

    @staticmethod
    def _normalize_urls(text: str) -> str:
        """
        Converts URLs into spoken-friendly format (e.g. 'google.com' -> 'google dot com').
        """
        def _replace_url(match: re.Match) -> str:
            raw_url = match.group(0)
            clean = re.sub(r"^https?://(?:www\.)?", "", raw_url, flags=re.IGNORECASE)
            clean = clean.split("?")[0].rstrip("/")  # Remove query params
            parts = clean.split("/")
            domain = parts[0]
            spoken_domain = domain.replace(".", " dot ")
            if len(parts) > 1 and parts[1]:
                return f"{spoken_domain} slash {' '.join(parts[1:])}"
            return spoken_domain

        url_pattern = r"https?://[^\s]+"
        text = re.sub(url_pattern, _replace_url, text)

        # Standalone domain names (e.g. example.com)
        domain_pattern = r"\b([a-zA-Z0-9-]+\.(?:com|org|in|net|edu|gov))\b"
        text = re.sub(domain_pattern, lambda m: m.group(1).replace(".", " dot "), text)
        return text

    @staticmethod
    def _normalize_numbers_and_ips(text: str) -> str:
        """
        Normalizes IP addresses and percent signs for natural speech.
        """
        # IP address (e.g. 127.0.0.1 -> 127 point 0 point 0 point 1)
        ip_pattern = r"\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b"
        text = re.sub(ip_pattern, r"\1 point \2 point \3 point \4", text)

        # Percentages (e.g. 50% -> 50 percent)
        text = re.sub(r"(\d+)%", r"\1 percent", text)

        return text

    @classmethod
    def _normalize_hinglish_to_devanagari(cls, text: str) -> str:
        """
        Contextually converts common Hinglish grammar tokens to Devanagari script,
        while strictly preserving English technical and borrowed terms.
        Example:
        'Aapka order confirm ho gaya hai' -> 'आपका order confirm हो गया है'
        """
        tokens = text.split()
        converted: List[str] = []

        for token in tokens:
            # Strip trailing punctuation for dictionary check
            match = re.match(r"^([a-zA-Z0-9'-]+)([.,!?;:]*)$", token)
            if not match:
                converted.append(token)
                continue

            word = match.group(1)
            punct = match.group(2)
            word_lower = word.lower()

            # If technical term, preserve in English
            if word_lower in PRESERVED_TECH_TERMS:
                converted.append(f"{word}{punct}")
            # If recognized Hinglish token, replace with Devanagari
            elif word_lower in HINGLISH_TO_DEVANAGARI:
                deva = HINGLISH_TO_DEVANAGARI[word_lower]
                converted.append(f"{deva}{punct}")
            else:
                converted.append(f"{word}{punct}")

        return " ".join(converted)
