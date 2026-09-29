"""Queue-free recording: the graph is memory, answer check, and progress view, not a work queue.

Countdown-island (Muse Spark, n=4 per arm) showed the pop/expand queue adding calls and seeded
rival busywork without improving answers, so `record` writes graph progress directly."""

import json
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


class RecordModeTests(unittest.TestCase):
    def ok(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)

    def start(self, tmp_dir: str) -> Path:
        state_path = Path(tmp_dir) / "state.json"
        self.ok(run_cli("init", "--goal", "Explain the failure", "-o", str(state_path)))
        return state_path

    def record(self, state_path: Path, patch: dict) -> subprocess.CompletedProcess[str]:
        patch_path = state_path.with_name("patch.json")
        patch_path.write_text(json.dumps(patch), encoding="utf-8")
        return run_cli("record", str(state_path), "--patch", str(patch_path))

    def solved_trail(self, state_path: Path, observation_score: int) -> None:
        self.ok(self.record(state_path, {
            "nodes": [
                {"id": "T1", "type": "test", "text": "Probe the system"},
                {"id": "O1", "type": "observation", "text": "Probe output", "source": "probe.log", "quote": "exit 3", "note": "Only the last run was logged", "score": observation_score},
            ],
            "edges": [edge("T1", "O1", "leads_to")],
        }))
        self.ok(self.record(state_path, {
            "answer": "CS1",
            "nodes": [{"id": "CS1", "type": "candidate_solution", "text": "Root cause", "answer_kind": "exact_answer"}],
            "edges": [edge("O1", "CS1", "leads_to"), edge("CS1", "G1", "answers")],
        }))

    def test_record_renders_live_view(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 5)

            live_view = state_path.with_suffix(".html").read_text(encoding="utf-8")
            self.assertIn("CS1", live_view)
            self.assertIn("exit 3", live_view)
            self.assertIn("Only the last run was logged", live_view)

    def test_record_leaves_live_view_untouched_when_the_view_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 5)
            live_view_path = state_path.with_suffix(".html")
            before = live_view_path.stat()

            self.ok(self.record(state_path, {"update_nodes": [{"id": "O1", "set": {"score": 5}}]}))
            unchanged = live_view_path.stat()
            self.assertEqual((unchanged.st_ino, unchanged.st_mtime_ns), (before.st_ino, before.st_mtime_ns))

            self.ok(self.record(state_path, {"nodes": [{"id": "C1", "type": "constraint", "text": "Keep the API", "source": "user prompt"}]}))
            self.assertIn("Keep the API", live_view_path.read_text(encoding="utf-8"))

    def test_record_checks_quotes_against_a_local_source_file(self) -> None:
        # Issue #35: stitched or trimmed quotes went unnoticed, so the CLI checks them verbatim.
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            Path(tmp_dir, "case.md").write_text(
                "## Section 8\n\n"
                "- Railing screws partly sawed or filed; not fresh? maybe bright metal visible.\n"
                "- Dr. Saye was seen with Mira, then “checking sedatives” until 20:43.\n\n"
                "> Four bells argue, three bells lie,  \n"
                "> two bells swear, and one asks why.\n",
                encoding="utf-8",
            )

            def observation(node_id: str, quote: str, source: str = "case.md Section 8") -> dict:
                return {"id": node_id, "type": "observation", "text": "Seen in the case file", "source": source, "quote": quote, "score": 5}

            # Line breaks, blockquote markers, quote-mark style, and ellipsis-joined fragments are not edits.
            self.ok(self.record(state_path, {"nodes": [
                observation("O1", "Four bells argue, three bells lie, two bells swear"),
                observation("O2", "Railing screws partly sawed or filed ... then 'checking sedatives' until 20:43"),
            ]}))
            # A source that is not a local file cannot be checked and stays free-form.
            self.ok(self.record(state_path, {"nodes": [
                observation("O3", "anything", source="https://example.com/report"),
            ]}))

            before = state_path.read_text(encoding="utf-8")
            trimmed_hedge = self.record(state_path, {"nodes": [observation("O4", "Railing screws partly sawed or filed; bright metal visible")]})
            stitched_update = self.record(state_path, {"update_nodes": [{"id": "O1", "set": {"quote": "Section 8: Railing screws partly sawed"}}]})

            for rejected, node_id in ((trimmed_hedge, "O4"), (stitched_update, "O1")):
                self.assertEqual(rejected.returncode, 1, rejected.stdout)
                self.assertIn(node_id, rejected.stderr)
                self.assertIn("case.md", rejected.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_record_takes_no_frontier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)

            with_frontier = self.record(state_path, {"nodes": [{"id": "T1", "type": "test", "text": "Probe"}], "frontier": [{"id": "Q1", "node": "T1"}]})

            self.assertEqual(with_frontier.returncode, 1)
            self.assertIn("frontier", with_frontier.stderr)

    def test_grounded_answer_audits_without_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 5)

            audit = run_cli("audit", str(state_path))

            self.assertEqual(audit.returncode, 0, audit.stderr)
            self.assertNotIn("warning", audit.stdout + audit.stderr)

    def test_answer_needs_no_belief_level_and_no_review(self) -> None:
        # Issue #37: belief never separated right answers from wrong ones, and a same-model
        # reviewer shared the misreading, so neither is checked.
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 3)

            self.ok(run_cli("audit", str(state_path)))

    def test_answer_needs_every_test_result_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 5)
            self.ok(self.record(state_path, {"nodes": [{"id": "T2", "type": "test", "text": "Check the config"}]}))

            audit = run_cli("audit", str(state_path))

            self.assertEqual(audit.returncode, 1, audit.stdout)
            self.assertIn("T2", audit.stderr)

    def test_not_run_test_settles_the_result_check_and_shows_in_the_view(self) -> None:
        # Issue #35: an unrunnable check was answered with an invented result; not_run records it honestly.
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 5)
            self.ok(self.record(state_path, {"nodes": [
                {"id": "T2", "type": "test", "text": "Compare dental records", "not_run": "The case file has no dental records"},
            ]}))

            self.ok(run_cli("audit", str(state_path)))
            view = state_path.with_suffix(".html").read_text(encoding="utf-8")
            self.assertIn("not run", view)
            self.assertIn("The case file has no dental records", view)

    def test_not_run_is_only_a_reason_on_a_test_without_a_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 5)

            on_hypothesis = self.record(state_path, {"nodes": [{"id": "H1", "type": "hypothesis", "text": "Guess", "score": 3, "not_run": "x"}]})
            blank_reason = self.record(state_path, {"nodes": [{"id": "T2", "type": "test", "text": "Check", "not_run": " "}]})
            with_result = self.record(state_path, {"update_nodes": [{"id": "T1", "set": {"not_run": "Could not run it"}}]})

            for rejected in (on_hypothesis, blank_reason, with_result):
                self.assertEqual(rejected.returncode, 1, rejected.stdout)
                self.assertIn("not_run", rejected.stderr)

    def test_review_commands_are_gone(self) -> None:
        for command in ("review", "stop-review"):
            with self.subTest(command=command):
                result = run_cli(command, "state.json")
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("invalid choice", result.stderr)


if __name__ == "__main__":
    unittest.main()
