"""Knowledge base retrieval tool using markdown files."""

from pathlib import Path
from config.settings import KNOWLEDGE_DIR
from loguru import logger


def load_knowledge(locale: str = "zh", category: str = None) -> str:
    """Load knowledge base content for a locale and optional category."""
    kb_dir = KNOWLEDGE_DIR / locale
    if not kb_dir.exists():
        kb_dir = KNOWLEDGE_DIR / "zh"  # fallback

    if category:
        fpath = kb_dir / f"{category}.md"
        if fpath.exists():
            return fpath.read_text(encoding="utf-8")
        return ""

    # Load all knowledge files
    texts = []
    for f in sorted(kb_dir.glob("*.md")):
        texts.append(f.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(texts)


def search_knowledge(query: str, locale: str = "zh") -> str:
    """Simple keyword search across knowledge files."""
    kb_dir = KNOWLEDGE_DIR / locale
    if not kb_dir.exists():
        kb_dir = KNOWLEDGE_DIR / "zh"

    results = []
    query_lower = query.lower()
    for f in kb_dir.glob("*.md"):
        content = f.read_text(encoding="utf-8")
        if query_lower in content.lower():
            # Extract relevant paragraph
            for para in content.split("\n\n"):
                if query_lower in para.lower():
                    results.append(para.strip())
                    break

    if results:
        return "\n\n".join(results[:3])

    if locale == "zh":
        return "知识库中未找到相关信息。"
    return "No relevant information found in the knowledge base."
