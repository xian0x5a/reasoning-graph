"""Check observation quotes verbatim against the local text file their source names.

A reviewer model passed stitched and hedge-trimmed quotes (issue #35), so when `source` starts
with a readable local text file, every ellipsis-separated fragment of `quote` must appear in it.
Other sources (URLs, commands, binary files, prose) stay free-form and unchecked.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

ELLIPSIS_SEPARATOR = re.compile(r"\[\.\.\.\]|\.\.\.|…")
BLOCKQUOTE_MARKER = re.compile(r"(?m)^[ \t]*>[ \t]?")
QUOTE_MARK = re.compile(r"[\"'‘’“”]")
EMPHASIS_MARK = re.compile(r"[*_`]")
WHITESPACE = re.compile(r"\s+")
FRAGMENT_EDGE_PUNCTUATION = " .,;:'"


def _normalize(text: str) -> str:
    """Erase differences that are formatting, not wording: line breaks, markdown markers, quote-mark style, case."""
    text = BLOCKQUOTE_MARKER.sub("", text)
    text = QUOTE_MARK.sub("'", text)
    text = EMPHASIS_MARK.sub("", text)
    return WHITESPACE.sub(" ", text).strip().lower()


def local_source_file(source: Any, base_dir: Path) -> tuple[str, Path] | None:
    """Return (file name, path) when the source's first token names a local file."""
    tokens = str(source or "").split()
    if not tokens:
        return None
    file_name = tokens[0].rstrip(",;:")
    path = base_dir / file_name
    return (file_name, path) if path.is_file() else None


def _local_source_text(source: Any, base_dir: Path) -> tuple[str, str] | None:
    """Return (file name, text) when the source's first token names a readable local text file."""
    local_file = local_source_file(source, base_dir)
    if local_file is None:
        return None
    file_name, path = local_file
    try:
        return file_name, path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def quote_mismatch_messages(node: dict[str, Any], base_dir: Path) -> list[str]:
    """Name each quote fragment of an observation that its local source file does not contain."""
    quote = node.get("quote")
    if node.get("type") != "observation" or not isinstance(quote, str) or not quote.strip():
        return []
    source = _local_source_text(node.get("source"), base_dir)
    if source is None:
        return []
    file_name, source_text = source
    normalized_source = _normalize(source_text)
    messages = []
    for fragment in ELLIPSIS_SEPARATOR.split(quote):
        normalized_fragment = _normalize(fragment).strip(FRAGMENT_EDGE_PUNCTUATION)
        if normalized_fragment and normalized_fragment not in normalized_source:
            messages.append(
                f"observation {node.get('id')} quote is not verbatim in {file_name}: {fragment.strip()!r}; "
                "copy the exact text and join separate excerpts with '...'"
            )
    return messages
