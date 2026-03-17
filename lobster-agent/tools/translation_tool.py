"""Language detection and translation tool."""

import re


def detect_language(text: str) -> str:
    """Simple language detection: zh or en."""
    # Count Chinese characters
    cn_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    total_chars = len(text.strip())
    if total_chars == 0:
        return "zh"
    if cn_chars / total_chars > 0.3:
        return "zh"
    return "en"
