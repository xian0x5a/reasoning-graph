"""Sum up the reader eval per view.

    uv run tests/scenarios/exact-answer/score_reader.py <item-dir>... [--by-item]

Reads what run_reader.py wrote. Per view:

trace  key points traced to a verbatim, relevant story passage, out of all key points read
catch  plants caught, on planted views; findings filed as real or spurious, on planted and
       clean views; and how long the view is
kinds  per view and plant kind, plants caught, caught as the first finding, and their mean rank
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

from run_reader import VIEWS


def reads(item_dir: Path, task: str) -> list[dict]:
    return [
        {**json.loads(path.read_text(encoding="utf-8")), "item": item_dir.name}
        for path in sorted((item_dir / "reader" / task).glob("*.json"))
    ]


def trace_rows(results: list[dict]) -> list[str]:
    rows = [f"{'trace':<12}{'traced':>12}{'verbatim':>12}{'chars':>9}{'cost':>8}"]
    for view in VIEWS:
        view_reads = [read for read in results if read["view"] == view]
        if not view_reads:
            continue
        traced = sum(read["traced"] for read in view_reads)
        total = sum(read["key_points"] for read in view_reads)
        quotes = [point for read in view_reads for point in read["points"] if point["quote"]]
        verbatim = sum(point["in_record"] and point["in_story"] for point in quotes)
        rows.append(
            f"{view:<12}{f'{traced}/{total}':>12}{f'{verbatim}/{len(quotes)}':>12}"
            f"{mean(read['record_chars'] for read in view_reads):>9.0f}"
            f"{sum(read['reader_cost'] + read['judge_cost'] for read in view_reads):>8.2f}"
        )
    return rows


def catch_rows(results: list[dict]) -> list[str]:
    rows = [f"{'catch':<12}{'caught':>10}{'rank':>6}{'real p/c':>10}{'spurious p/c':>14}{'chars':>9}{'cost':>8}"]
    for view in VIEWS:
        planted = [read for read in results if read["view"] == view and read["condition"] == "planted"]
        clean = [read for read in results if read["view"] == view and read["condition"] == "clean"]
        if not planted and not clean:
            continue
        ranks = [read["caught_rank"] for read in planted if read["caught"]]
        rows.append(
            f"{view:<12}{f'{len(ranks)}/{len(planted)}':>10}{(mean(ranks) if ranks else 0):>6.1f}"
            f"{f'{sum(read['real'] for read in planted)}/{sum(read['real'] for read in clean)}':>10}"
            f"{f'{sum(read['spurious'] for read in planted)}/{sum(read['spurious'] for read in clean)}':>14}"
            f"{mean(read['record_chars'] for read in planted + clean):>9.0f}"
            f"{sum(read['reader_cost'] + read['judge_cost'] for read in planted + clean):>8.2f}"
        )
    return rows


def kind_rows(results: list[dict], plant_kinds: dict[str, str]) -> list[str]:
    """Readers list five findings nearly always, so where the plant ranks tells more than whether it is caught."""
    rows = [f"{'kinds':<12}{'kind':<14}{'caught':>8}{'first':>7}{'rank':>6}"]
    for view in VIEWS:
        for kind in sorted(set(plant_kinds.values())):
            planted = [read for read in results if read["view"] == view and read["condition"] == "planted"
                       and plant_kinds[read["item"]] == kind]
            if not planted:
                continue
            ranks = [read["caught_rank"] for read in planted if read["caught"]]
            rows.append(
                f"{view:<12}{kind:<14}{f'{len(ranks)}/{len(planted)}':>8}{f'{ranks.count(1)}':>7}"
                f"{(mean(ranks) if ranks else 0):>6.1f}"
            )
    return rows


def by_item_rows(trace: list[dict], catch: list[dict]) -> list[str]:
    """Per item and view: key points traced, and plants caught, summed over repeats."""
    cells: dict[str, dict[str, str]] = defaultdict(dict)
    for view in VIEWS:
        for item in sorted({read["item"] for read in trace + catch}):
            traced = [read for read in trace if read["item"] == item and read["view"] == view]
            planted = [read for read in catch if read["item"] == item and read["view"] == view and read["condition"] == "planted"]
            trace_cell = f"{sum(read['traced'] for read in traced)}/{sum(read['key_points'] for read in traced)}" if traced else "-"
            catch_cell = f"{sum(read['caught'] for read in planted)}/{len(planted)}" if planted else "-"
            cells[item][view] = f"{trace_cell} {catch_cell}"
    header = f"{'item (traced caught)':<36}" + "".join(f"{view:>14}" for view in VIEWS)
    return [header] + [f"{item[:35]:<36}" + "".join(f"{cells[item][view]:>14}" for view in VIEWS) for item in sorted(cells)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("item_dirs", nargs="+", type=Path)
    parser.add_argument("--by-item", action="store_true")
    args = parser.parse_args()
    trace = [read for item_dir in args.item_dirs for read in reads(item_dir, "trace")]
    catch = [read for item_dir in args.item_dirs for read in reads(item_dir, "catch")]
    plant_kinds = {
        item_dir.name: json.loads(plants.read_text(encoding="utf-8"))["kind"]
        for item_dir in args.item_dirs if (plants := item_dir / "reader" / "plants.json").exists()
    }
    lines = trace_rows(trace) + [""] + catch_rows(catch) + [""] + kind_rows(catch, plant_kinds)
    if args.by_item:
        lines += [""] + by_item_rows(trace, catch)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
