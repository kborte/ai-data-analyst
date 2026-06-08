from dataclasses import dataclass
from pathlib import Path

SUPPORTED_EXTENSIONS = {".txt", ".md"}
PREVIEW_CHAR_LIMIT = 500


@dataclass
class TextLoadResult:
    content: str
    preview: str
    char_count: int
    line_count: int


def load_text(path: Path | str) -> TextLoadResult:
    """
    Read a .txt or .md file. Returns full content and a short preview.
    No LLM summarisation — that is a later milestone.
    """
    p = Path(path)
    if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported text extension: {p.suffix!r}. Expected {SUPPORTED_EXTENSIONS}.")
    content = p.read_text(encoding="utf-8")
    return TextLoadResult(
        content=content,
        preview=content[:PREVIEW_CHAR_LIMIT],
        char_count=len(content),
        line_count=content.count("\n") + (1 if content else 0),
    )
