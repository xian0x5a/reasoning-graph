"""Draft the flaw the reader eval plants in each view of an item.

    uv run tests/scenarios/exact-answer/draft_plants.py <item-dir>... [--model <model-id>]

Writes <item-dir>/reader/plants.json from the views reader_views.py wrote. The kind of flaw
alternates by item, in name order among the items given, so pass them all in one call:

overclaim     an observation in the case for the answer states more than its quote and the
              story give; the same stronger statement goes into the transcript and the notes
wrong_weight  an observation that does not bear on the answer supports it at score 5; the
              transcript and the notes call that clue strong support

A draft is only a draft: each plant is checked by hand against the story before a catch run.
An item that has its plants.json is skipped.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from model_call import structured_call

DEFAULT_MODEL = "claude-opus-5-5"
KINDS = ("overclaim", "wrong_weight")

KIND_TASK = {
    "overclaim": """Plant an overclaim. Pick one observation node that appears under "Why believe it" in
the page, whose fact the notes also state if any such node exists. Rewrite its text so it states
a concrete detail the story does not give, as fact, in a way that makes the case for the answer
stronger. Leave its quote alone, so the quote no longer covers the text. Set `node_id` and
`new_text`; leave `edge_from` and `edge_to` empty.

In the transcript, replace the node's original text wherever it appears with the new text,
copying each occurrence exactly, JSON escapes included. In the notes, make the line that states
the same fact state the same detail.""",
    "wrong_weight": """Plant a wrong weight. Pick one observation node whose fact does not bear on which
answer is right: a detail about something else, or a clue that only matters for another
question. Add a `supports` edge, score 5, from it to the answer's candidate node or to a
hypothesis under "Why believe it". Set `edge_from` and `edge_to`; leave `node_id` and `new_text`
empty.

In the transcript, add one sentence to the agent's own text in its last session calling that
clue strong support for the answer. In the notes, add one line calling it the same.""",
}

PLANT_PROMPT = """We are testing whether a reader can find a flaw in someone's record of their
reasoning about a detective puzzle. You will plant one flaw in three records of the same solved
puzzle: the page (a view of their reasoning graph), the transcript of their sessions, and their
notes. A reader gets one record and the answer, without the story, and is asked to find flaws.

{kind_task}

Rules for every plant:
- The flaw must be real against the story: check it there.
- Write in the voice of the record around it, at its length. The plant must not stand out by
  style, only by substance.
- Change nothing else.
- Edits are exact find-and-replace: `find` is copied character for character from the record,
  and every occurrence is replaced. To add text, find an anchor and replace it with the anchor
  plus the new text.
- When the notes do not state the fact you picked, plant the same kind of flaw on a fact they
  do state, and describe it in its own `flaw`.

Each `flaw` says, in one or two sentences for a grader holding the story, what was changed and
why it is wrong.

# Story

{story}

# Page

{page}

# Transcript

{transcript}

# Notes

{notes}
"""

EDITS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {"find": {"type": "string"}, "replace": {"type": "string"}},
        "required": ["find", "replace"],
        "additionalProperties": False,
    },
}

PLANT_SCHEMA = {
    "type": "object",
    "properties": {
        "page_flaw": {"type": "string"},
        "node_id": {"type": "string"},
        "new_text": {"type": "string"},
        "edge_from": {"type": "string"},
        "edge_to": {"type": "string"},
        "transcript_flaw": {"type": "string"},
        "transcript_edits": EDITS_SCHEMA,
        "notes_flaw": {"type": "string"},
        "notes_edits": EDITS_SCHEMA,
    },
    "required": ["page_flaw", "node_id", "new_text", "edge_from", "edge_to",
                 "transcript_flaw", "transcript_edits", "notes_flaw", "notes_edits"],
    "additionalProperties": False,
}


def page_plant(kind: str, drafted: dict) -> dict:
    if kind == "overclaim":
        return {"flaw": drafted["page_flaw"], "node": drafted["node_id"], "text": drafted["new_text"]}
    return {"flaw": drafted["page_flaw"], "edge": {"from": drafted["edge_from"], "to": drafted["edge_to"],
                                                   "type": "supports", "score": 5}}


def draft_plant(item_dir: Path, kind: str, model: str) -> dict:
    views_dir = item_dir / "reader" / "views"
    prompt = PLANT_PROMPT.format(
        kind_task=KIND_TASK[kind],
        story=(item_dir / "problem.md").read_text(encoding="utf-8"),
        page=(views_dir / "page.txt").read_text(encoding="utf-8"),
        transcript=(views_dir / "transcript.txt").read_text(encoding="utf-8"),
        notes=(views_dir / "notes.txt").read_text(encoding="utf-8"),
    )
    drafted = structured_call(prompt, PLANT_SCHEMA, model)
    return {
        "kind": kind,
        "views": {
            "page": page_plant(kind, drafted),
            "transcript": {"flaw": drafted["transcript_flaw"], "edits": drafted["transcript_edits"]},
            "notes": {"flaw": drafted["notes_flaw"], "edits": drafted["notes_edits"]},
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("item_dirs", nargs="+", type=Path)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    for index, item_dir in enumerate(sorted(item_dir.resolve() for item_dir in args.item_dirs)):
        path = item_dir / "reader" / "plants.json"
        if path.exists():
            print(f"skip  {item_dir.name}")
            continue
        plant = draft_plant(item_dir, KINDS[index % len(KINDS)], args.model)
        path.write_text(json.dumps(plant, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"done  {item_dir.name} ({plant['kind']})")


if __name__ == "__main__":
    main()
