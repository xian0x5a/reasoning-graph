"""A hand-edited state passes the checks a patch would before anything builds on it.

Agents edited state.json with Python in 15 of 22 #34 runs, and a hand edit went unchecked.
It is checked, not logged: the state keeps no trace (issue #38)."""

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


def edge(source: str, target: str, edge_type: str, **extra: int) -> dict:
    return {"id": f"{source}-{target}", "from": source, "to": target, "type": edge_type, **extra}


def observation(node_id: str, quote: str) -> dict:
    return {"id": node_id, "type": "observation", "text": quote, "source": "problem.md", "quote": quote, "score": 5}


def story_patch(hypothesis_score: int) -> dict:
    """A graph whose candidate rests on one hypothesis, claimed as the answer."""
    return {
        "answer": "CS1",
        "nodes": [
            observation("O1", "The butler left at nine"),
            observation("O2", "The gardener stayed late, or so he said"),
            {"id": "H1", "type": "hypothesis", "text": "The gardener did it", "score": hypothesis_score},
            {"id": "H2", "type": "hypothesis", "text": "The butler did it", "score": 1},
            {"id": "CS1", "type": "candidate_solution", "text": "The gardener", "answer_kind": "exact_answer"},
        ],
        "edges": [
            edge("O2", "H1", "supports", score=4),
            edge("O1", "H2", "contradicts", score=3),
            edge("H1", "CS1", "leads_to"),
            edge("CS1", "G1", "answers"),
        ],
    }


class HandEditTests(unittest.TestCase):
    def ok(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)

    def fails(self, result: subprocess.CompletedProcess[str], *expected: str) -> None:
        self.assertEqual(result.returncode, 1, result.stdout)
        for text in expected:
            self.assertIn(text, result.stderr)

    def start(self, tmp_dir: str, hypothesis_score: int = 4) -> Path:
        state_path = Path(tmp_dir) / "state.json"
        Path(tmp_dir, "problem.md").write_text(SOURCE_TEXT, encoding="utf-8")
        self.ok(run_cli("init", "--goal", "Who did it?", "-o", str(state_path)))
        self.ok(self.record(state_path, story_patch(hypothesis_score)))
        return state_path

    def record(self, state_path: Path, patch: dict) -> subprocess.CompletedProcess[str]:
        patch_path = state_path.with_name("patch.json")
        patch_path.write_text(json.dumps(patch), encoding="utf-8")
        return run_cli("record", str(state_path), "--patch", str(patch_path))

    def load(self, state_path: Path) -> dict:
        return json.loads(state_path.read_text(encoding="utf-8"))

    def node(self, state: dict, node_id: str) -> dict:
        return next(node for node in state["nodes"] if node["id"] == node_id)

    def hand_edit(self, state_path: Path, edit) -> None:
        state = self.load(state_path)
        edit(state)
        state_path.write_text(json.dumps(state), encoding="utf-8")

    def test_refresh_checks_a_hand_edit_and_rewrites_the_views(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)

            def drop_edge_and_lower_score(state: dict) -> None:
                state["edges"] = [item for item in state["edges"] if item["id"] != "O1-H2"]
                self.node(state, "O2")["score"] = 3

            self.hand_edit(state_path, drop_edge_and_lower_score)
            edited = state_path.read_text(encoding="utf-8")
            self.ok(run_cli("refresh", str(state_path)))

            self.assertEqual(state_path.read_text(encoding="utf-8"), edited)
            index = state_path.with_suffix(".index.md").read_text(encoding="utf-8")
            self.assertNotIn("O1 -contradicts", index)
            self.assertIn("O2 observation (score 3)", index)

    def test_refresh_rejects_a_hand_edited_quote_that_is_not_verbatim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.hand_edit(state_path, lambda state: self.node(state, "O1").update({"quote": "The butler left at ten"}))
            before = state_path.read_text(encoding="utf-8")

            self.fails(run_cli("refresh", str(state_path)), "O1", "problem.md")
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_record_builds_on_a_hand_edit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.hand_edit(state_path, lambda state: self.node(state, "H2").update({"score": 2}))

            self.ok(self.record(state_path, {"update_nodes": [{"id": "H1", "set": {"note": "Only his word"}}]}))

            state = self.load(state_path)
            self.assertEqual(self.node(state, "H2")["score"], 2)
            self.assertEqual(self.node(state, "H1")["note"], "Only his word")

    def test_record_and_audit_recheck_a_hand_edited_quote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.hand_edit(state_path, lambda state: self.node(state, "O1").update({"quote": "The butler left at ten"}))
            before = state_path.read_text(encoding="utf-8")

            self.fails(self.record(state_path, {"update_nodes": [{"id": "H1", "set": {"note": "x"}}]}), "O1", "problem.md")
            self.fails(run_cli("audit", str(state_path)), "O1", "problem.md")
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_audit_reports_quote_and_answer_failures_together(self) -> None:
        # Fixing a quote only to learn of a failed answer check on the next run cost the agent a turn.
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.ok(self.record(state_path, {"nodes": [{"id": "T1", "type": "test", "text": "Ask the cook"}]}))
            self.hand_edit(state_path, lambda state: self.node(state, "O1").update({"quote": "The butler left at ten"}))

            self.fails(run_cli("audit", str(state_path)), "O1", "problem.md", "without a recorded result observation: T1")


if __name__ == "__main__":
    unittest.main()
