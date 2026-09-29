"""Write the three views a reader checks an answer from, for the reader eval (issue #39).

    uv --project packages/reasoning-graph run python tests/scenarios/exact-answer/reader_views.py <item-dir>...

For each item, from the last round of run `s55-loop-r1`, into <item-dir>/reader/views/:

    page.txt         the case-first page of the graph run, as the text a reader sees
    transcript.txt   the graph run's sessions: the agent's text, its tool calls and their results
    notes.txt        notes.md of the notes-file run
    graph-answer.md  the answer the page and the transcript explain
    notes-answer.md  the answer the notes explain

The page drops what a text reader cannot use: scripts, styles, the graph drawing and its
Mermaid source. The transcript drops the skill text the harness injects and the grader's
feedback turns, which neither memory view shows as such.
"""

from __future__ import annotations

import argparse
import json
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from reasoning_graph.mermaid import to_mermaid
from reasoning_graph.page import html_document

RUN_ID = "s55-loop-r1"
VIEW_NAMES = ("page", "transcript", "notes")
# Four agents never set summary.answer, so their pages would open without a case. The
# candidate each claims here is the one its passed answer.md names by letter.
UNCLAIMED_ANSWERS = {
    "sweat-it-out": "C2",
    "death-at-andersonville": "C_d",
    "mystery-of-the-bratty-kid": "C_a",
    "the-secret-in-the-old-trunk": "C1",
}
SKILL_TEXT_PREFIX = "Base directory for this skill:"


def last_round(item_dir: Path, arm: str) -> Path:
    loop = json.loads((item_dir / arm / RUN_ID / "loop.json").read_text(encoding="utf-8"))
    return item_dir / arm / RUN_ID / "rounds" / str(len(loop["rounds"]))


def rounds(item_dir: Path, arm: str) -> list[Path]:
    final = last_round(item_dir, arm)
    return [final.parent / str(number) for number in range(1, int(final.name) + 1)]


class _PageText(HTMLParser):
    """The visible text of the page, one block per line, lists indented by depth."""

    HIDDEN = {"script", "style", "svg", "template", "nav", "dialog"}
    # The graph section holds only the drawing and its controls; the node cards follow it.
    HIDDEN_CLASSES = {"graph-section", "graph-source"}
    BLOCKS = {"p", "div", "section", "article", "h1", "h2", "h3", "h4", "summary", "tr", "dt", "dd", "pre", "br"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = [""]
        self.hidden_depth = 0
        self.list_depth = 0
        # Tags whose content is dropped by class, with the depth of each open one.
        self.skipped: list[str] = []

    def break_line(self, prefix: str = "") -> None:
        if self.lines[-1].strip():
            self.lines.append("")
        self.lines[-1] = prefix

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = (dict(attrs).get("class") or "").split()
        if self.skipped or tag in self.HIDDEN or self.HIDDEN_CLASSES.intersection(classes):
            self.skipped.append(tag)
            return
        if tag in ("ul", "ol"):
            self.list_depth += 1
        elif tag == "li":
            self.break_line("  " * (self.list_depth - 1) + "- ")
        elif tag == "blockquote":
            self.break_line("  " * self.list_depth + "> ")
        elif tag == "cite":
            self.lines[-1] += " —"
        elif tag in self.BLOCKS:
            self.break_line()

    def handle_endtag(self, tag: str) -> None:
        if self.skipped:
            if self.skipped[-1] == tag:
                self.skipped.pop()
            return
        if tag in ("ul", "ol"):
            self.list_depth -= 1
        if tag in self.BLOCKS or tag in ("li", "blockquote", "ul", "ol"):
            self.break_line()

    def handle_data(self, data: str) -> None:
        if self.skipped:
            return
        text = " ".join(data.split())
        if text:
            joiner = " " if self.lines[-1] and not self.lines[-1].endswith((" ", "> ")) else ""
            self.lines[-1] += joiner + text

    def text(self) -> str:
        return "\n".join(line.rstrip() for line in self.lines if line.strip()) + "\n"


def page_text(state: dict[str, Any]) -> str:
    parser = _PageText()
    parser.feed(html_document(state, to_mermaid(state), render_mode="offline"))
    return parser.text()


def current_schema(state: dict[str, Any]) -> dict[str, Any]:
    """Drop the fields the schema removed since this run, which the page reports as failed checks."""
    state = {key: value for key, value in state.items() if key not in ("stop_policy", "events")}
    state["edges"] = [{key: value for key, value in edge.items() if key != "id"} for edge in state["edges"]]
    return state


def claimed_state(item_dir: Path) -> dict[str, Any]:
    state = current_schema(json.loads((last_round(item_dir, "graph") / "state.json").read_text(encoding="utf-8")))
    if not state.get("summary", {}).get("answer"):
        state["summary"] = {**state.get("summary", {}), "answer": UNCLAIMED_ANSWERS[item_dir.name]}
    return state


def tool_call_text(block: dict[str, Any]) -> str:
    tool_input = block["input"]
    if block["name"] == "Bash":
        return f"[call Bash]\n{tool_input['command']}"
    return f"[call {block['name']}]\n{json.dumps(tool_input, ensure_ascii=False, indent=1)}"


def session_text(transcript: Path) -> list[str]:
    parts = []
    for line in transcript.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("type") not in ("assistant", "user"):
            continue
        for block in event["message"]["content"]:
            if block["type"] == "text" and event["type"] == "assistant":
                parts.append(f"[agent]\n{block['text']}")
            elif block["type"] == "tool_use":
                parts.append(tool_call_text(block))
            elif block["type"] == "tool_result":
                parts.append(f"[result]\n{block['content']}")
            # Thinking is redacted in these transcripts, and the only user text is the skill.
            elif block["type"] == "text" and not block["text"].startswith(SKILL_TEXT_PREFIX):
                raise ValueError(f"unexpected user text in {transcript}")
    return parts


def transcript_text(item_dir: Path) -> str:
    sections = []
    for round_dir in rounds(item_dir, "graph"):
        parts = session_text(round_dir / "transcript.jsonl")
        sections.append(f"===== Session {round_dir.name} =====\n\n" + "\n\n".join(parts))
    return "\n\n".join(sections) + "\n"


def item_views(item_dir: Path) -> dict[str, str]:
    """Each view's text, and the answer each one explains."""
    graph_round, notes_round = last_round(item_dir, "graph"), last_round(item_dir, "notes-file")
    return {
        "page.txt": page_text(claimed_state(item_dir)),
        "transcript.txt": transcript_text(item_dir),
        "notes.txt": (notes_round / "notes.md").read_text(encoding="utf-8"),
        "graph-answer.md": (graph_round / "answer.md").read_text(encoding="utf-8"),
        "notes-answer.md": (notes_round / "answer.md").read_text(encoding="utf-8"),
    }


def write_views(item_dir: Path) -> None:
    views_dir = item_dir / "reader" / "views"
    views_dir.mkdir(parents=True, exist_ok=True)
    for name, text in item_views(item_dir).items():
        (views_dir / name).write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("item_dirs", nargs="+", type=Path)
    for item_dir in parser.parse_args().item_dirs:
        write_views(item_dir.resolve())
        print(f"wrote {item_dir}/reader/views")


if __name__ == "__main__":
    main()
