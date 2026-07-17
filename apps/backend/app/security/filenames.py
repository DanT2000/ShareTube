"""Safe filename handling — prevents path traversal and executable extensions."""
from __future__ import annotations

import os
import re
import unicodedata

from .ssrf import BLOCKED_EXTENSIONS

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_DOTS = re.compile(r"\.{2,}")


def sanitize_filename(name: str, *, default: str = "file", max_len: int = 180) -> str:
    """Return a filesystem-safe basename. Strips directories, control chars,
    traversal sequences, and neutralises executable extensions.
    """
    name = name or ""
    # Drop any directory component (both separators).
    name = name.replace("\\", "/").split("/")[-1]
    name = unicodedata.normalize("NFKC", name)
    name = _UNSAFE.sub("_", name)
    name = _DOTS.sub(".", name).strip(" .")
    if not name:
        name = default

    root, ext = os.path.splitext(name)
    ext_lower = ext.lower()
    if ext_lower in BLOCKED_EXTENSIONS:
        ext = ext + ".bin"
    if not root:
        root = default

    # Truncate keeping extension.
    if len(root) > max_len:
        root = root[:max_len]
    result = root + ext
    # Reserved windows-ish names guard (harmless on linux, safer everywhere).
    if result.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL"}:
        result = "_" + result
    return result


def safe_join(base_dir: str, *paths: str) -> str:
    """Join under base_dir and guarantee the result stays inside it."""
    base = os.path.realpath(base_dir)
    target = os.path.realpath(os.path.join(base, *paths))
    if target != base and not target.startswith(base + os.sep):
        raise ValueError("path traversal detected")
    return target
