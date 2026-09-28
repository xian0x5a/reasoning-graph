"""A hand-edited state is re-synced with `refresh`, and the stop gate computes what it checks itself.

Agents edited state.json with Python in 15 of 22 #34 runs. A hand edit after a passing review
left the review current, and stored beliefs were trusted until something validated them."""

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


def edge(source: str, target: str, edge_type: str, **extra: float) -> dict:
    return {"id": f"{source}-{target}", "from": source, "to": target, "type": edge_type, "reasoning": "Test edge.", **extra}


def observation(node_id: str, quote: str) -> dict:
    return {"id": node_id, "type": "observation", "text": quote, "source": "problem.md", "quote": quote, "prior": 0.95}


def story_patch(hypothesis_prior: float) -> dict:
    """A graph whose candidate clears the 0.8 threshold only when the hypothesis prior is high."""
    return {
        "reason": "Read the story",
        "nodes": [
            observation("O1", "The butler left at nine"),
            observation("O2", "The gardener stayed late, or so he said"),
            {"id": "H1", "type": "hypothesis", "text": "The gardener did it", "prior": hypothesis_prior},
            {"id": "H2", "type": "hypothesis", "text": "The butler did it", "prior": 0.2},
            {"id": "CS1", "type": "candidate_solution", "text": "The gardener", "answer_kind": "exact_answer"},
        ],
        "edges": [
            edge("O2", "H1", "supports", likelihood_ratio=3),
            edge("O1", "H2", "contradicts", likelihood_ratio=0.5),
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

    def start(self, tmp_dir: str, hypothesis_prior: float = 0.85) -> Path:
        state_path = Path(tmp_dir) / "state.json"
        Path(tmp_dir, "problem.md").write_text(SOURCE_TEXT, encoding="utf-8")
        self.ok(run_cli("init", "--goal", "Who did it?", "--strict", "-o", str(state_path)))
        self.ok(self.record(state_path, story_patch(hypothesis_prior)))
        return state_path

    def record(self, state_path: Path, patch: dict) -> subprocess.CompletedProcess[str]:
        patch_path = state_path.with_name("patch.json")
        patch_path.write_text(json.dumps(patch), encoding="utf-8")
        return run_cli("record", str(state_path), "--patch", str(patch_path))

    def review(self, state_path: Path) -> subprocess.CompletedProcess[str]:
        return run_cli("review", str(state_path), "--reviewer", "reviewer-1", "--verdict", "pass", "--findings", "Quotes match.")

    def stop(self, state_path: Path, outcome: str = "solved") -> subprocess.CompletedProcess[str]:
        return run_cli("stop", str(state_path), "--reason", "CS1 is grounded and reviewed", "--outcome", outcome)

    def load(self, state_path: Path) -> dict:
        return json.loads(state_path.read_text(encoding="utf-8"))

    def node(self, state: dict, node_id: str) -> dict:
        return next(node for node in state["nodes"] if node["id"] == node_id)

    def hand_edit(self, state_path: Path, edit) -> None:
        state = self.load(state_path)
        edit(state)
        state_path.write_text(json.dumps(state), encoding="utf-8")

    def test_refresh_logs_hand_removals_and_recomputes_beliefs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)

            def drop_edge_and_lower_prior(state: dict) -> None:
                state["edges"] = [item for item in state["edges"] if item["id"] != "O1-H2"]
                self.node(state, "O2")["prior"] = 0.6

            self.hand_edit(state_path, drop_edge_and_lower_prior)
            self.fails(run_cli("validate", str(state_path)), "stale belief", "refresh")
            self.ok(run_cli("refresh", str(state_path)))

            state = self.load(state_path)
            event = state["events"][-1]
            self.assertEqual(event["action"], "refresh")
            self.assertEqual(event["remove_edges"], ["O1-H2"])
            self.assertEqual(self.node(state, "O2")["belief"], 0.6)
            self.ok(run_cli("validate", str(state_path)))
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

    def test_record_refuses_a_hand_edited_state_until_refreshed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.hand_edit(state_path, lambda state: self.node(state, "H2").update({"prior": 0.1}))
            note = {"reason": "Note", "update_nodes": [{"id": "H1", "set": {"note": "Only his word"}}]}

            self.fails(self.record(state_path, note), "refresh")
            self.ok(run_cli("refresh", str(state_path)))
            self.ok(self.record(state_path, note))

    def test_stop_refuses_a_graph_changed_after_its_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.ok(self.review(state_path))
            self.hand_edit(state_path, lambda state: self.node(state, "H1").update({"prior": 0.95}))

            self.fails(self.stop(state_path), "refresh")
            self.ok(run_cli("refresh", str(state_path)))
            self.fails(self.stop(state_path), "changed after the latest review")
            self.ok(self.review(state_path))
            self.ok(self.stop(state_path))
            self.ok(run_cli("audit", str(state_path)))

    def test_stop_recomputes_beliefs_instead_of_trusting_stored_ones(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir, hypothesis_prior=0.3)
            self.ok(self.review(state_path))
            self.hand_edit(state_path, lambda state: self.node(state, "CS1").update({"belief": 0.99}))

            self.fails(self.stop(state_path), "belief_threshold")
            self.ok(self.stop(state_path, "inconclusive"))

            stopped = self.load(state_path)
            self.assertLess(self.node(stopped, "CS1")["belief"], 0.8)
            self.ok(run_cli("audit", str(state_path)))

    def test_audit_catches_an_edit_after_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.ok(self.review(state_path))
            self.ok(self.stop(state_path))
            self.hand_edit(state_path, lambda state: self.node(state, "CS1").update({"text": "The butler"}))

            self.fails(run_cli("audit", str(state_path)), "changed after stop")


if __name__ == "__main__":
    unittest.main()
