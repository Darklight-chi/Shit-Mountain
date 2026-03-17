"""Language detection tool — supports zh, en, ru."""

import re


def detect_language(text: str) -> str:
    """Detect language: zh, ru, or en."""
    stripped = text.strip()
    if not stripped:
        return "zh"

    total = len(stripped)
    cn_chars = len(re.findall(r'[\u4e00-\u9fff]', stripped))
    ru_chars = len(re.findall(r'[\u0400-\u04ff]', stripped))

    if cn_chars / total > 0.3:
        return "zh"
    if ru_chars / total > 0.3:
        return "ru"
    return "en"
