"""Computed belief is for the reader of the rendered graph; the state and the agent-facing
commands hold none of it (issue #37).

Belief did not separate right answers from wrong ones, and an agent that sees it tunes scores
until a number moves. So the state stores no belief, no command prints one, and `audit`
judges the candidate the answer names instead of the top-ranked one."""

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )


def edge(source: str, target: str, edge_type: str, **extra: int) -> dict:
    return {"from": source, "to": target, "type": edge_type, **extra}


def candidate(node_id: str, text: str) -> dict:
    return {"id": node_id, "type": "candidate_solution", "text": text, "answer_kind": "exact_answer"}


# CS1 rests on a probe result and ranks first. CS2 rests on a weaker clue. CS3 rests on nothing.
STORY_PATCH = {
    "nodes": [
        {"id": "T1", "type": "test", "text": "Check the greenhouse log"},
        {"id": "O1", "type": "observation", "text": "The gardener signed in at nine", "source": "greenhouse log"},
        {"id": "O2", "type": "observation", "text": "The butler had the key", "source": "housekeeper"},
        candidate("CS1", "The gardener"),
        candidate("CS2", "The butler"),
        candidate("CS3", "The cook"),
    ],
    "edges": [
        edge("T1", "O1", "leads_to"),
        edge("O1", "CS1", "leads_to"),
        edge("O2", "CS2", "supports"),
        edge("CS1", "G1", "answers"),
        edge("CS2", "G1", "answers"),
        edge("CS3", "G1", "answers"),
    ],
}
NUMBER = re.compile(r"\d\.\d")


class StateCase(unittest.TestCase):
    def ok(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)

    def fails(self, result: subprocess.CompletedProcess[str], *expected: str) -> None:
        self.assertEqual(result.returncode, 1, result.stdout)
        for text in expected:
            self.assertIn(text, result.stderr)

    def start(self, tmp_dir: str, answer: str = "") -> Path:
        state_path = Path(tmp_dir) / "state.json"
        self.ok(run_cli("init", "--goal", "Who did it?", "-o", str(state_path)))
        self.ok(self.record(state_path, STORY_PATCH | {"answer": answer}))
        return state_path

    def record(self, state_path: Path, patch: dict) -> subprocess.CompletedProcess[str]:
        patch_path = state_path.with_name("patch.json")
        patch_path.write_text(json.dumps(patch), encoding="utf-8")
        return run_cli("record", str(state_path), "--patch", str(patch_path))

    def audit(self, state_path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return run_cli("audit", str(state_path), *extra)

    def load(self, state_path: Path) -> dict:
        return json.loads(state_path.read_text(encoding="utf-8"))

    def edit(self, state_path: Path, change) -> None:
        state = self.load(state_path)
        change(state)
        state_path.write_text(json.dumps(state), encoding="utf-8")


class BeliefOutOfStateTests(StateCase):
    def test_state_written_by_record_and_refresh_holds_no_computed_belief(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.assertNotIn("belief", state_path.read_text(encoding="utf-8"))

            self.edit(state_path, lambda state: state["nodes"][2].update({"score": 4}))
            refreshed = run_cli("refresh", str(state_path))

            self.ok(refreshed)
            self.assertNotIn("belief", refreshed.stdout)
            self.assertNotIn("belief", state_path.read_text(encoding="utf-8"))

    def test_state_or_patch_carrying_belief_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            before = state_path.read_text(encoding="utf-8")

            added = self.record(state_path, {"nodes": [{"id": "H1", "type": "hypothesis", "text": "Guess", "belief": 0.9}]})
            updated = self.record(state_path, {"update_nodes": [{"id": "O1", "set": {"belief": 0.9}}]})
            for rejected in (added, updated):
                self.fails(rejected, "belief was removed")
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

            self.edit(state_path, lambda state: state["nodes"][2].update({"belief": 0.9}))
            self.fails(run_cli("audit", str(state_path)), "node O1: belief was removed")

    def test_beliefs_command_is_gone(self) -> None:
        result = run_cli("beliefs", "state.json")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("invalid choice", result.stderr)

    def test_audit_shows_no_belief_and_no_ranking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir, answer="CS1")

            result = self.audit(state_path)

            self.ok(result)
            shown = result.stdout + result.stderr
            for word in ("belief", "rank"):
                self.assertNotIn(word, shown)
            self.assertIsNone(NUMBER.search(shown), shown)


class AnswerNamesACandidateTests(StateCase):
    def test_answer_may_name_a_grounded_candidate_that_is_not_top_ranked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir, answer="The butler did it.")

            self.ok(self.audit(state_path))

    def test_grounding_check_judges_the_named_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir, answer="CS3")

            self.fails(self.audit(state_path), "answer candidate CS3 is not evidence-grounded")


if __name__ == "__main__":
    unittest.main()
