"""Computed belief is for the reader of the rendered graph; the state and the agent-facing
commands hold none of it (issue #37).

Belief did not separate right answers from wrong ones, and an agent that sees it tunes scores
until a number moves. So the state stores no belief, no command prints one, and the stop gate
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
    return {"id": f"{source}-{target}", "from": source, "to": target, "type": edge_type, **extra}


def candidate(node_id: str, text: str) -> dict:
    return {"id": node_id, "type": "candidate_solution", "text": text, "answer_kind": "exact_answer"}


# CS1 rests on a probe result and ranks first. CS2 rests on a weaker clue. CS3 rests on nothing.
STORY_PATCH = {
    "reason": "Read the story and ran the probe",
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
        self.ok(run_cli("init", "--goal", "Who did it?", "--strict", "-o", str(state_path)))
        self.ok(self.record(state_path, STORY_PATCH))
        if answer:
            self.edit(state_path, lambda state: state["summary"].update({"answer": answer}))
        return state_path

    def record(self, state_path: Path, patch: dict) -> subprocess.CompletedProcess[str]:
        patch_path = state_path.with_name("patch.json")
        patch_path.write_text(json.dumps(patch), encoding="utf-8")
        return run_cli("record", str(state_path), "--patch", str(patch_path))

    def stop(self, state_path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return run_cli("stop", str(state_path), "--reason", "The answer rests on the log", "--outcome", "solved", *extra)

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

            added = self.record(state_path, {"reason": "r", "nodes": [{"id": "H1", "type": "hypothesis", "text": "Guess", "belief": 0.9}]})
            updated = self.record(state_path, {"reason": "r", "update_nodes": [{"id": "O1", "set": {"belief": 0.9}}]})
            for rejected in (added, updated):
                self.fails(rejected, "belief was removed")
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

            self.edit(state_path, lambda state: state["nodes"][2].update({"belief": 0.9}))
            self.fails(run_cli("validate", str(state_path)), "node O1: belief was removed")

    def test_report_rows_carry_no_computed_numbers(self) -> None:
        for field in ("belief", "truth_cost", "effective_truth_cost", "weight"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp_dir:
                state_path = self.start(tmp_dir)
                self.edit(state_path, lambda state: state.update({"report": {"candidates": [{"id": "CS1", field: 0.5}]}}))

                self.fails(run_cli("validate", str(state_path)), f"report.candidates[0].{field} was removed")

    def test_beliefs_command_is_gone(self) -> None:
        result = run_cli("beliefs", "state.json")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("invalid choice", result.stderr)

    def test_stop_audit_and_doctor_show_no_belief_and_no_ranking(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir, answer="CS1")

            stopped = self.stop(state_path)
            self.ok(stopped)
            outputs = [stopped, run_cli("audit", str(state_path)), run_cli("doctor", str(state_path))]

            for result in outputs:
                self.ok(result)
                shown = result.stdout + result.stderr
                for word in ("belief", "rank"):
                    self.assertNotIn(word, shown)
                self.assertIsNone(NUMBER.search(shown), shown)
            stopped_state = state_path.read_text(encoding="utf-8")
            self.assertEqual([event["action"] for event in self.load(state_path)["events"]], ["record", "stop"])
            self.assertNotIn("belief", stopped_state)

    def test_stop_takes_no_top_option(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir, answer="CS1")
            result = self.stop(state_path, "--top", "3")
            self.assertEqual(result.returncode, 2, result.stdout)
            self.assertIn("--top", result.stderr)

    def test_rank_event_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            rank = {"step": 9, "action": "rank", "best": "CS1", "belief": 0.9, "candidates": [{"node": "CS1", "belief": 0.9, "effective_truth_cost": 0.105361}]}
            self.edit(state_path, lambda state: state["events"].append(rank))

            self.fails(run_cli("validate", str(state_path)), "rank event", "removed")


class AnswerNamesACandidateTests(StateCase):
    def test_answer_may_name_a_grounded_candidate_that_is_not_top_ranked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir, answer="The butler did it.")
            draft = Path(tmp_dir) / "answer.md"
            draft.write_text("Final answer: The butler. The gardener signed in at nine, which clears him.", encoding="utf-8")

            self.ok(self.stop(state_path, "--draft", str(draft)))
            self.ok(run_cli("audit", str(state_path)))

    def test_grounding_gate_judges_the_named_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir, answer="CS3")

            self.fails(self.stop(state_path), "answer candidate CS3 is not evidence-grounded")

    def test_answer_must_name_a_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir, answer="The chauffeur did it.")

            self.fails(self.stop(state_path), "summary.answer names no candidate for goal G1", "CS1", "CS2", "CS3", "The chauffeur did it.")

    def test_solved_stop_needs_the_answer_to_name_one_of_several_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            empty = self.start(tmp_dir)
            self.fails(self.stop(empty), "goal G1 has 3 candidates", "name the one answer in summary.answer")

        with tempfile.TemporaryDirectory() as tmp_dir:
            ambiguous = self.start(tmp_dir, answer="CS1 or CS2")
            self.fails(self.stop(ambiguous), "names several candidates for goal G1: CS1, CS2", "name the one answer")

    def test_stop_takes_the_answer_as_an_option(self) -> None:
        # Without it, naming one of several candidates costs a hand edit of the state.
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)

            self.fails(self.stop(state_path, "--answer", "The chauffeur did it."), "summary.answer names no candidate for goal G1")
            self.assertEqual(self.load(state_path)["summary"]["answer"], "")

            self.ok(self.stop(state_path, "--answer", "CS1"))
            self.assertEqual(self.load(state_path)["summary"]["answer"], "CS1")
            self.ok(run_cli("audit", str(state_path)))

    def test_draft_must_name_the_answer_the_state_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir, answer="CS2")
            draft = Path(tmp_dir) / "answer.md"
            draft.write_text("Final answer: The gardener.", encoding="utf-8")

            self.fails(self.stop(state_path, "--draft", str(draft)), "draft does not mention candidate CS2 ('The butler') for goal G1")

    def test_candidate_id_is_matched_as_a_whole_word(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir, answer="CS10")

            self.fails(self.stop(state_path), "summary.answer names no candidate for goal G1")

    def test_audit_catches_an_answer_edited_after_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir, answer="CS1")
            self.ok(self.stop(state_path))
            self.edit(state_path, lambda state: state["summary"].update({"answer": "CS3"}))

            self.fails(run_cli("audit", str(state_path)), "answer candidate CS3 is not evidence-grounded")


if __name__ == "__main__":
    unittest.main()
