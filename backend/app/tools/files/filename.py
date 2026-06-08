import re
from pathlib import PurePosixPath


def make_safe_filename(original: str) -> str:
    """
    Convert an uploaded filename to a safe, flat filename.

    Prevents path traversal (../, absolute paths, backslashes).
    Replaces spaces and unsafe characters with underscores.
    Preserves the file extension.
    """
    # Take only the final path component to strip any directory prefix
    name = PurePosixPath(original.replace("\\", "/")).name

    # Split stem and suffix
    dot = name.rfind(".")
    if dot > 0:
        stem, ext = name[:dot], name[dot:]
    else:
        stem, ext = name, ""

    # Replace whitespace and non-word characters with underscores
    stem = re.sub(r"[^\w\-]", "_", stem)
    stem = re.sub(r"_+", "_", stem).strip("_") or "file"

    # Only allow alphanumeric and dot in extension
    ext = re.sub(r"[^\w.]", "", ext)

    return stem + ext
