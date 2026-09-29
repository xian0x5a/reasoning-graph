"""A hand-edited state passes the checks a patch would before anything builds on it.

Agents edited state.json with Python in 15 of 22 #34 runs. A hand edit went unlogged and
unchecked."""

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
        "reason": "Read the story",
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

    def test_refresh_logs_hand_removals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)

            def drop_edge_and_lower_score(state: dict) -> None:
                state["edges"] = [item for item in state["edges"] if item["id"] != "O1-H2"]
                self.node(state, "O2")["score"] = 3

            self.hand_edit(state_path, drop_edge_and_lower_score)
            self.ok(run_cli("refresh", str(state_path)))

            state = self.load(state_path)
            event = state["events"][-1]
            self.assertEqual(event["action"], "refresh")
            self.assertEqual(event["remove_edges"], ["O1-H2"])
            self.ok(run_cli("audit", str(state_path)))
            # A second refresh finds nothing new and adds no event.
            self.ok(run_cli("refresh", str(state_path)))
            self.assertEqual(len(self.load(state_path)["events"]), len(state["events"]))

    def test_refresh_rejects_a_hand_edited_quote_that_is_not_verbatim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.hand_edit(state_path, lambda state: self.node(state, "O1").update({"quote": "The butler left at ten"}))
            before = state_path.read_text(encoding="utf-8")

            self.fails(run_cli("refresh", str(state_path)), "O1", "problem.md")
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_record_logs_a_hand_edit_before_its_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)

            def drop_edge_and_lower_score(state: dict) -> None:
                state["edges"] = [item for item in state["edges"] if item["id"] != "O1-H2"]
                self.node(state, "H2")["score"] = 1

            self.hand_edit(state_path, drop_edge_and_lower_score)
            self.ok(self.record(state_path, {"reason": "Note", "update_nodes": [{"id": "H1", "set": {"note": "Only his word"}}]}))

            state = self.load(state_path)
            hand_edit, record = state["events"][-2:]
            self.assertEqual((hand_edit["action"], hand_edit["remove_edges"]), ("refresh", ["O1-H2"]))
            self.assertEqual(record["action"], "record")
            self.ok(run_cli("audit", str(state_path)))

    def test_record_and_audit_recheck_a_hand_edited_quote(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.hand_edit(state_path, lambda state: self.node(state, "O1").update({"quote": "The butler left at ten"}))
            before = state_path.read_text(encoding="utf-8")

            self.fails(self.record(state_path, {"reason": "Note", "update_nodes": [{"id": "H1", "set": {"note": "x"}}]}), "O1", "problem.md")
            self.fails(run_cli("audit", str(state_path)), "O1", "problem.md")
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_audit_reports_quote_and_answer_failures_together(self) -> None:
        # Fixing a quote only to learn of a failed answer check on the next run cost the agent a turn.
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.ok(self.record(state_path, {"reason": "Planned a check", "nodes": [{"id": "T1", "type": "test", "text": "Ask the cook"}]}))
            self.hand_edit(state_path, lambda state: self.node(state, "O1").update({"quote": "The butler left at ten"}))

            self.fails(run_cli("audit", str(state_path)), "O1", "problem.md", "without a recorded result observation: T1")


if __name__ == "__main__":
    unittest.main()
