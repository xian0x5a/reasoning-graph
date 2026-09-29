"""Link each source that names a local file, so a reader can open the context around a quote.

The #39 reader eval found that a reader who cannot see the story doubts quotes it has no way
to check. The link is relative when the file sits under the page's directory, since the two
then move together, and an absolute file URI otherwise, which survives moving the page alone.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import quote

from .source_quotes import local_source_file


class SourceLink(NamedTuple):
    file_name: str
    href: str


def file_href(path: Path, page_dir: Path | None) -> str:
    path = path.resolve()
    if page_dir is not None and path.is_relative_to(page_dir.resolve()):
        return quote(path.relative_to(page_dir.resolve()).as_posix())
    return path.as_uri()


def source_links(state: dict[str, Any], source_base_dir: Path, page_dir: Path | None) -> dict[str, SourceLink]:
    """Each node source that names a local file, with the link to that file from a page in `page_dir`
    (None when the page has no place on disk)."""
    links = {}
    for node in state.get("nodes", []):
        if not isinstance(node, dict) or not node.get("source"):
            continue
        source = str(node["source"])
        if (local_file := local_source_file(source, source_base_dir)) is not None:
            file_name, path = local_file
            links[source] = SourceLink(file_name, file_href(path, page_dir))
    return links


def source_html(source: str, links: dict[str, SourceLink]) -> str:
    """The source as page text, with its file name a link when it names a local file."""
    link = links.get(source)
    if link is None:
        return html.escape(source)
    head, _, rest = source.partition(link.file_name)
    return (
        f'{html.escape(head)}<a class="source-link" href="{html.escape(link.href)}">'
        f"{html.escape(link.file_name)}</a>{html.escape(rest)}"
    )
