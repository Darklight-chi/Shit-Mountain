"""Knowledge base retrieval tool using markdown files."""

from config.settings import KNOWLEDGE_DIR


def load_knowledge(locale: str = "zh", category: str | None = None) -> str:
    """Load knowledge base content for a locale and optional category."""
    kb_dir = KNOWLEDGE_DIR / locale
    if not kb_dir.exists():
        kb_dir = KNOWLEDGE_DIR / "zh"

    if category:
        fpath = kb_dir / f"{category}.md"
        if fpath.exists():
            return fpath.read_text(encoding="utf-8")
        return ""

    texts = []
    for fpath in sorted(kb_dir.glob("*.md")):
        texts.append(fpath.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(texts)


def search_knowledge(query: str, locale: str = "zh") -> str:
    """Simple keyword search across knowledge files."""
    kb_dir = KNOWLEDGE_DIR / locale
    if not kb_dir.exists():
        kb_dir = KNOWLEDGE_DIR / "zh"

    results = []
    query_lower = query.lower()
    for fpath in kb_dir.glob("*.md"):
        content = fpath.read_text(encoding="utf-8")
        if query_lower not in content.lower():
            continue
        for para in content.split("\n\n"):
            if query_lower in para.lower():
                results.append(para.strip())
                break

    if results:
        return "\n\n".join(results[:3])
    return ""
