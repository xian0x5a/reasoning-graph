"""`record` keeps a compact index beside the state: what the agent rereads after a context
reset, and what a subagent reads, instead of the whole JSON (issue #37)."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
SOURCE_TEXT = "The butler left at nine. The gardener stayed late, or so he said.\n"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )


def edge(source: str, target: str, edge_type: str, **extra: object) -> dict:
    return {"id": f"{source}-{target}", "from": source, "to": target, "type": edge_type, **extra}


STORY_PATCH = {
    "reason": "Read the story",
    "nodes": [
        {"id": "O1", "type": "observation", "text": "The butler left at nine", "source": "problem.md", "quote": "The butler left at nine"},
        {"id": "O2", "type": "observation", "text": "The gardener says he stayed late", "source": "problem.md", "quote": "stayed late, or so he said", "score": 3},
        {"id": "T1", "type": "test", "text": "Check the greenhouse log"},
        {"id": "O3", "type": "observation", "text": "The log shows the gardener at ten", "source": "greenhouse log"},
        {"id": "H1", "type": "hypothesis", "text": "The gardener did it", "score": 4, "note": "Only his word so far"},
        {"id": "H2", "type": "hypothesis", "text": "The butler did it"},
        {"id": "H3", "type": "hypothesis", "text": "The gardener was in the house at ten"},
        {"id": "T2", "type": "test", "text": "Ask the cook"},
        {"id": "T3", "type": "test", "text": "Compare dental records", "not_run": "The case file has none"},
        {"id": "C1", "type": "constraint", "text": "Name one person", "source": "user prompt"},
        {"id": "CS1", "type": "candidate_solution", "text": "The gardener", "answer_kind": "exact_answer"},
    ],
    "edges": [
        edge("T1", "O3", "leads_to"),
        edge("O3", "H3", "leads_to"),
        edge("O2", "H1", "supports"),
        edge("O3", "H1", "supports"),
        edge("O1", "H2", "contradicts", score=5, note="Nine is before the theft"),
        {"id": "E9", "from": "H1", "to": "CS1", "type": "leads_to"},
        edge("CS1", "G1", "answers"),
    ],
    "factors": [{"id": "F1", "edges": ["O2-H1", "O3-H1"], "score": 4, "note": "Both place him on site"}],
}


class IndexFileTests(unittest.TestCase):
    def ok(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)

    def start(self, tmp_dir: str) -> Path:
        state_path = Path(tmp_dir) / "state.json"
        Path(tmp_dir, "problem.md").write_text(SOURCE_TEXT, encoding="utf-8")
        self.ok(run_cli("init", "--goal", "Who did it?", "-o", str(state_path)))
        self.ok(self.record(state_path, STORY_PATCH))
        return state_path

    def record(self, state_path: Path, patch: dict, *extra: str) -> subprocess.CompletedProcess[str]:
        patch_path = state_path.with_name("patch.json")
        patch_path.write_text(json.dumps(patch), encoding="utf-8")
        return run_cli("record", str(state_path), "--patch", str(patch_path), *extra)

    def index(self, state_path: Path) -> str:
        return state_path.with_suffix(".index.md").read_text(encoding="utf-8")

    def test_record_refreshes_the_index_beside_the_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.assertEqual(state_path.with_suffix(".index.md").name, "state.index.md")
            self.assertNotIn("The cook saw nothing", self.index(state_path))

            self.ok(self.record(state_path, {
                "reason": "Asked the cook",
                "nodes": [{"id": "O4", "type": "observation", "text": "The cook saw nothing", "source": "interview"}],
                "edges": [edge("T2", "O4", "leads_to")],
            }))

            index = self.index(state_path)
            self.assertIn("- O4 observation: The cook saw nothing [interview]", index)
            self.assertIn("Last record: Asked the cook", index)

    def test_goals_come_first_then_what_is_open_then_the_rest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            lines = self.index(self.start(tmp_dir)).splitlines()

            def line_of(text: str) -> int:
                return next(number for number, line in enumerate(lines) if line.startswith(text))

            goal = line_of("- G1 goal: Who did it?")
            open_section, nodes_section, edges_section = line_of("## Open"), line_of("## Nodes"), line_of("## Edges")
            self.assertLess(goal, open_section)
            self.assertLess(open_section, nodes_section)
            self.assertLess(nodes_section, edges_section)

            open_lines = lines[open_section + 1:nodes_section]
            self.assertEqual([line for line in open_lines if line], [
                "- H1 hypothesis (score 4): The gardener did it | note: Only his word so far",
                "- H2 hypothesis: The butler did it",
                "- T2 test (no result): Ask the cook",
                "- T3 test (not run: The case file has none): Compare dental records",
            ])
            # A hypothesis that rests on premises and a test with a result are settled.
            settled = lines[nodes_section + 1:edges_section]
            self.assertIn("- H3 hypothesis: The gardener was in the house at ten", settled)
            self.assertIn("- T1 test: Check the greenhouse log", settled)

    def test_index_shows_scores_only_where_they_depart_from_the_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index = self.index(self.start(tmp_dir))

            self.assertIn("- O1 observation: The butler left at nine [problem.md]", index)
            self.assertIn("- O2 observation (score 3): The gardener says he stayed late [problem.md]", index)
            self.assertIn("- C1 constraint: Name one person [user prompt]", index)
            self.assertIn("- CS1 candidate_solution: The gardener", index)
            self.assertIn("- O1 -contradicts(5)-> H2 | note: Nine is before the theft", index)
            self.assertIn("- O2 -supports-> H1", index)
            # An edge id that is not from-to is given, since patches and groups refer to it.
            self.assertIn("- H1 -leads_to-> CS1 [E9]", index)
            self.assertIn("- F1 [O2-H1, O3-H1] score 4 | note: Both place him on site", index)

    def test_index_holds_no_quotes_and_no_computed_belief(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            index = self.index(self.start(tmp_dir))

            self.assertNotIn("or so he said", index)
            self.assertNotIn("belief", index)
            self.assertNotRegex(index, r"\d\.\d")

    def test_index_is_much_smaller_than_the_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.assertLess(len(self.index(state_path)), len(state_path.read_text(encoding="utf-8")) / 2)

    def test_refresh_rewrites_the_index_after_a_hand_edit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            next(node for node in state["nodes"] if node["id"] == "H2")["text"] = "The butler had help"
            state_path.write_text(json.dumps(state), encoding="utf-8")

            self.ok(run_cli("refresh", str(state_path)))

            self.assertIn("- H2 hypothesis: The butler had help", self.index(state_path))

    def test_index_follows_the_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            before = self.index(state_path)
            note = {"reason": "Noted a doubt", "update_nodes": [{"id": "H2", "set": {"note": "No motive"}}]}

            self.ok(self.record(state_path, note, "-o", str(Path(tmp_dir) / "next.json")))
            self.assertIn("No motive", Path(tmp_dir, "next.index.md").read_text(encoding="utf-8"))
            self.assertEqual(self.index(state_path), before)

            self.ok(self.record(state_path, note, "-o", "-"))
            self.assertEqual(sorted(path.name for path in Path(tmp_dir).glob("*.index.md")), ["next.index.md", "state.index.md"])


if __name__ == "__main__":
    unittest.main()
