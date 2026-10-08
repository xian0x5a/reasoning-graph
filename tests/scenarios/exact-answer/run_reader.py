"""The reader eval: a model checks an answer from one view of its reasoning.

    uv run tests/scenarios/exact-answer/run_reader.py trace <item-dir>... [--repeats 3]
    uv run tests/scenarios/exact-answer/run_reader.py catch <item-dir>... [--repeats 3]

Reads the views reader_views.py wrote. The reader gets the answer and one view, never the
story, and no tools.

trace  For each rubric key point, the reader copies the story passage the view shows for it.
       A point is traced when the passage is in the view and in the story (checked by text,
       no model), and a judge holding the story agrees the passage is the clue of the point.
catch  The reader lists up to five flaws in the reasoning, on the planted view and on the
       clean one. A judge holding the story and the plant files each finding as the plant,
       another real flaw, or spurious.

Each read lands in <item-dir>/reader/<task>/<view>[.<condition>].r<n>.json; a read that has
its file is skipped, so a rerun only fills gaps.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from model_call import model_call

READER_MODEL = "claude-opus-5-5"
JUDGE_MODEL = "claude-opus-5-5"
VIEWS = ("page", "transcript", "notes")
ANSWER_OF_VIEW = {"page": "graph-answer.md", "transcript": "graph-answer.md", "notes": "notes-answer.md"}
CATCH_CONDITIONS = ("planted", "clean")
MAX_FINDINGS = 5
PARALLEL_READS = int(os.environ.get("RG_BENCH_PARALLEL", "6"))

# Saying the puzzle is published fiction keeps the safety classifier from refusing the short
# notes records: without it, three items' notes reads (a poisoning, a child) are refused every time.
READER_SYSTEM_PROMPT = (
    "You check someone else's reasoning about a published detective puzzle: short fiction written "
    "for readers to solve, from a puzzle collection. Answer only with the requested JSON."
)

RECORD_INTRO = """Someone solved a detective puzzle and wrote the answer below. With it comes the record
they kept of their reasoning. You do not have the story itself, only the record."""

TRACE_PROMPT = RECORD_INTRO + """

Check where the answer's key points come from. For each key point, find in the record the
passage of the story that the point rests on, and copy it into `quote` character for
character, as the record shows it. Copy only text the record presents as the story's own
words: do not paraphrase, and do not rebuild a passage the record does not show. Leave
`quote` empty when the record shows no such passage. In `where`, say where in the record you
found it: a node id, or the part of the record.

# Answer

{answer}

# Key points

{key_points}

# Record

{record}
"""

CATCH_PROMPT = RECORD_INTRO + """

Check the reasoning for flaws of two kinds:

- overclaim: a statement of what the story says claims more than the story passage it
  quotes or cites supports;
- wrong weight: evidence is treated as support for a conclusion, or as strong support, when
  it does not bear on that conclusion or bears on it only weakly.

List up to {max_findings} flaws, the most serious first. For each, give `where`, a node id or a
short excerpt copied from the record, and `why`. A record may have no flaw of either kind;
then list none.

# Answer

{answer}

# Record

{record}
"""

JUDGE_SYSTEM_PROMPT = "You are a careful grader of detective puzzles. Answer only with the requested JSON."

TRACE_JUDGE_PROMPT = """A reader was asked, for each key point of a detective puzzle's answer, to give the
passage of the story the point rests on. Below are the story, the key points, and the
passages the reader gave. For each passage, decide whether it states the clue the key point
rests on, or part of it (`bears`: true), or is beside the point (`bears`: false).

# Story

{story}

# Key points and passages

{passages}
"""

CATCH_JUDGE_PROMPT = """A reader checked a record of someone's reasoning about a detective puzzle for flaws:
overclaims, where a statement of what the story says goes beyond the passage it quotes or
cites, and wrong weights, where evidence is treated as support, or strong support, for a
conclusion it does not bear on or bears on only weakly.

{plant_section}
File each finding the reader reported:

- `planted`: it points at the planted flaw above, at its place or its content;
- `real`: it points at another place, and the record really has that flaw there, judged
  against the story;
- `spurious`: the record does not have the flaw the finding claims.

# Story

{story}

# Record the reader checked

{record}

# Findings

{findings}
"""

PLANT_SECTION = """One flaw was planted in this record on purpose:

{flaw}
"""
NO_PLANT_SECTION = "No flaw was planted in this record: `planted` does not apply.\n"

TRACE_SCHEMA = {
    "type": "object",
    "properties": {
        "points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "quote": {"type": "string"}, "where": {"type": "string"}},
                "required": ["id", "quote", "where"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["points"],
    "additionalProperties": False,
}

TRACE_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "bears": {"type": "boolean"}, "why": {"type": "string"}},
                "required": ["id", "bears", "why"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}

CATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "maxItems": MAX_FINDINGS,
            "items": {
                "type": "object",
                "properties": {"where": {"type": "string"}, "why": {"type": "string"}},
                "required": ["where", "why"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["findings"],
    "additionalProperties": False,
}

CATCH_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "finding": {"type": "integer"},
                    "category": {"type": "string", "enum": ["planted", "real", "spurious"]},
                    "why": {"type": "string"},
                },
                "required": ["finding", "category", "why"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}

QUOTE_MARKS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
ELLIPSIS = re.compile(r"\.\.\.|…")


def normalized(text: str) -> str:
    """Text with straight quotes and dashes, one space between words, lower case."""
    return " ".join(text.translate(QUOTE_MARKS).split()).lower()


def found_in(quote: str, text: str) -> bool:
    """Whether every part of `quote` between ellipses is in `text`. Quote marks and punctuation
    at the ends of a part are ignored: a quoted clause often ends in a period the story lacks."""
    target = normalized(text)
    parts = [part.strip(" \"'.,;:!?") for part in ELLIPSIS.split(normalized(quote))]
    parts = [part for part in parts if part]
    return bool(parts) and all(part in target for part in parts)


def story_of(item_dir: Path) -> str:
    return (item_dir / "problem.md").read_text(encoding="utf-8")


def view_text(item_dir: Path, view: str, condition: str = "clean") -> str:
    views_dir = item_dir / "reader" / "views"
    return ((views_dir / "planted" if condition == "planted" else views_dir) / f"{view}.txt").read_text(encoding="utf-8")


def answer_of(item_dir: Path, view: str) -> str:
    return (item_dir / "reader" / "views" / ANSWER_OF_VIEW[view]).read_text(encoding="utf-8")


def key_points_text(item_dir: Path) -> tuple[list[dict], str]:
    key_points = json.loads((item_dir / "rubric.json").read_text(encoding="utf-8"))["key_points"]
    return key_points, "\n".join(f"- {point['id']}: {point['point']}" for point in key_points)


def trace_read(item_dir: Path, view: str) -> dict:
    key_points, key_points_listing = key_points_text(item_dir)
    record = view_text(item_dir, view)
    story = story_of(item_dir)
    read = model_call(
        TRACE_PROMPT.format(answer=answer_of(item_dir, view), key_points=key_points_listing, record=record),
        TRACE_SCHEMA, READER_MODEL, READER_SYSTEM_PROMPT,
    )
    quotes = {entry["id"]: entry for entry in read["structured_output"]["points"]}
    points = []
    for key_point in key_points:
        quote = quotes.get(key_point["id"], {}).get("quote", "").strip()
        points.append({
            "id": key_point["id"], "quote": quote, "where": quotes.get(key_point["id"], {}).get("where", ""),
            # A passage counts only when the reader copied it from the view and it is the story's own text.
            "in_record": bool(quote) and found_in(quote, record),
            "in_story": bool(quote) and found_in(quote, story),
        })
    judged = [point for point in points if point["in_record"] and point["in_story"]]
    judge_cost = 0.0
    bears: dict[str, dict] = {}
    if judged:
        points_by_id = {point["id"]: point for point in key_points}
        passages = "\n\n".join(f"- {point['id']}: {points_by_id[point['id']]['point']}\n  Passage: {point['quote']}" for point in judged)
        judgement = model_call(TRACE_JUDGE_PROMPT.format(story=story, passages=passages), TRACE_JUDGE_SCHEMA,
                               JUDGE_MODEL, JUDGE_SYSTEM_PROMPT)
        judge_cost = judgement["total_cost_usd"]
        bears = {verdict["id"]: verdict for verdict in judgement["structured_output"]["verdicts"]}
    for point in points:
        verdict = bears.get(point["id"])
        point["bears"] = bool(verdict and verdict["bears"])
        point["judge_why"] = verdict["why"] if verdict else ""
        point["traced"] = point["in_record"] and point["in_story"] and point["bears"]
    return {
        "view": view, "record_chars": len(record), "points": points,
        "traced": sum(point["traced"] for point in points), "key_points": len(points),
        "reader_cost": read["total_cost_usd"], "judge_cost": judge_cost,
    }


def plant_of(item_dir: Path) -> dict:
    return json.loads((item_dir / "reader" / "plants.json").read_text(encoding="utf-8"))


def catch_read(item_dir: Path, view: str, condition: str) -> dict:
    record = view_text(item_dir, view, condition)
    read = model_call(
        CATCH_PROMPT.format(answer=answer_of(item_dir, view), record=record, max_findings=MAX_FINDINGS),
        CATCH_SCHEMA, READER_MODEL, READER_SYSTEM_PROMPT,
    )
    findings = read["structured_output"]["findings"][:MAX_FINDINGS]
    judge_cost = 0.0
    categories: dict[int, dict] = {}
    if findings:
        plant = plant_of(item_dir)
        plant_section = PLANT_SECTION.format(flaw=plant["views"][view]["flaw"]) if condition == "planted" else NO_PLANT_SECTION
        listing = "\n\n".join(
            f"{number}. Where: {finding['where']}\n   Why: {finding['why']}" for number, finding in enumerate(findings, 1)
        )
        judgement = model_call(
            CATCH_JUDGE_PROMPT.format(plant_section=plant_section, story=story_of(item_dir), record=record, findings=listing),
            CATCH_JUDGE_SCHEMA, JUDGE_MODEL, JUDGE_SYSTEM_PROMPT,
        )
        judge_cost = judgement["total_cost_usd"]
        categories = {verdict["finding"]: verdict for verdict in judgement["structured_output"]["verdicts"]}
    for number, finding in enumerate(findings, 1):
        verdict = categories.get(number, {"category": "spurious", "why": "not judged"})
        # A clean record has no plant, so the judge's `planted` there is a misfiling.
        finding["category"] = verdict["category"] if condition == "planted" or verdict["category"] != "planted" else "spurious"
        finding["judge_why"] = verdict["why"]
    planted_ranks = [number for number, finding in enumerate(findings, 1) if finding["category"] == "planted"]
    return {
        "view": view, "condition": condition, "record_chars": len(record), "findings": findings,
        "caught": bool(planted_ranks), "caught_rank": planted_ranks[0] if planted_ranks else None,
        "real": sum(finding["category"] == "real" for finding in findings),
        "spurious": sum(finding["category"] == "spurious" for finding in findings),
        "reader_cost": read["total_cost_usd"], "judge_cost": judge_cost,
    }


def read_jobs(task: str, item_dirs: list[Path], repeats: int) -> list[tuple[Path, str, str | None, int]]:
    conditions = CATCH_CONDITIONS if task == "catch" else (None,)
    return [
        (item_dir, view, condition, repeat)
        for item_dir in item_dirs for view in VIEWS for condition in conditions for repeat in range(1, repeats + 1)
    ]


def result_path(task: str, item_dir: Path, view: str, condition: str | None, repeat: int) -> Path:
    condition_part = f".{condition}" if condition else ""
    return item_dir / "reader" / task / f"{view}{condition_part}.r{repeat}.json"


def run_job(task: str, job: tuple[Path, str, str | None, int]) -> str:
    item_dir, view, condition, repeat = job
    path = result_path(task, item_dir, view, condition, repeat)
    if path.exists():
        return f"skip  {path.relative_to(item_dir.parent)}"
    # The safety classifier refuses a call now and then, some of them on every try, so one
    # failed read is reported and the rest still run; a rerun retries what is missing.
    try:
        result = trace_read(item_dir, view) if task == "trace" else catch_read(item_dir, view, condition)
    except (subprocess.TimeoutExpired, RuntimeError) as error:
        return f"FAIL  {path.relative_to(item_dir.parent)}: {str(error)[:200]}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return f"done  {path.relative_to(item_dir.parent)}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task", choices=("trace", "catch"))
    parser.add_argument("item_dirs", nargs="+", type=Path)
    parser.add_argument("--repeats", type=int, default=1)
    args = parser.parse_args()
    jobs = read_jobs(args.task, [item_dir.resolve() for item_dir in args.item_dirs], args.repeats)
    failed = 0
    with ThreadPoolExecutor(PARALLEL_READS) as pool:
        for line in pool.map(lambda job: run_job(args.task, job), jobs):
            print(line, flush=True)
            failed += line.startswith("FAIL")
    if failed:
        raise SystemExit(f"{failed} reads failed; run again to retry them")


if __name__ == "__main__":
    main()
