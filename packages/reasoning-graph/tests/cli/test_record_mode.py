"""Queue-free recording: the graph is memory, stop gate, and progress view, not a work queue.

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


def edge(source: str, target: str, edge_type: str, **extra: float) -> dict:
    return {"id": f"{source}-{target}", "from": source, "to": target, "type": edge_type, "reasoning": "Test edge.", **extra}


class RecordModeTests(unittest.TestCase):
    def ok(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)

    def start(self, tmp_dir: str) -> Path:
        state_path = Path(tmp_dir) / "state.json"
        self.ok(run_cli("init", "--goal", "Explain the failure", "--strict", "-o", str(state_path)))
        return state_path

    def record(self, state_path: Path, patch: dict) -> subprocess.CompletedProcess[str]:
        patch_path = state_path.with_name("patch.json")
        patch_path.write_text(json.dumps(patch), encoding="utf-8")
        return run_cli("record", str(state_path), "--patch", str(patch_path))

    def solved_trail(self, state_path: Path, observation_prior: float) -> None:
        self.ok(self.record(state_path, {
            "reason": "Ran the probe",
            "nodes": [
                {"id": "T1", "type": "test", "text": "Probe the system"},
                {"id": "O1", "type": "observation", "text": "Probe output", "source": "probe.log", "quote": "exit 3", "prior": observation_prior},
            ],
            "edges": [edge("T1", "O1", "leads_to")],
        }))
        self.ok(self.record(state_path, {
            "reason": "Concluded from the probe",
            "nodes": [{"id": "CS1", "type": "candidate_solution", "text": "Root cause", "answer_kind": "exact_answer"}],
            "edges": [edge("O1", "CS1", "leads_to"), edge("CS1", "G1", "answers")],
        }))

    def stop(self, state_path: Path, outcome: str = "solved") -> subprocess.CompletedProcess[str]:
        return run_cli("stop", str(state_path), "--reason", "CS1 is grounded and confident", "--outcome", outcome)

    def test_record_logs_progress_and_renders_live_view(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 0.95)

            state = json.loads(state_path.read_text(encoding="utf-8"))
            records = [event for event in state["events"] if event["action"] == "record"]
            self.assertEqual([event["reason"] for event in records], ["Ran the probe", "Concluded from the probe"])
            self.assertEqual(records[0]["add_nodes"], ["T1", "O1"])
            self.assertIn("CS1", state_path.with_suffix(".html").read_text(encoding="utf-8"))

    def test_record_requires_reason_and_takes_no_frontier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            node = {"id": "T1", "type": "test", "text": "Probe"}

            missing_reason = self.record(state_path, {"nodes": [node]})
            with_frontier = self.record(state_path, {"reason": "r", "nodes": [node], "frontier": [{"id": "Q1", "node": "T1"}]})

            self.assertEqual(missing_reason.returncode, 1)
            self.assertIn("reason", missing_reason.stderr)
            self.assertEqual(with_frontier.returncode, 1)
            self.assertIn("frontier", with_frontier.stderr)

    def test_grounded_confident_answer_stops_and_audits_without_queue_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 0.95)

            self.ok(self.stop(state_path))
            audit = run_cli("audit", str(state_path))

            self.assertEqual(audit.returncode, 0, audit.stderr)
            self.assertNotIn("warning", audit.stdout + audit.stderr)

    def test_solved_stop_needs_the_belief_threshold(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 0.6)

            stopped = self.stop(state_path)

            self.assertEqual(stopped.returncode, 1, stopped.stdout)
            self.assertIn("belief_threshold", stopped.stderr)
            self.ok(self.stop(state_path, "inconclusive"))

    def test_solved_stop_needs_every_test_result_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 0.95)
            self.ok(self.record(state_path, {"reason": "Planned a check", "nodes": [{"id": "T2", "type": "test", "text": "Check the config"}]}))

            stopped = self.stop(state_path)

            self.assertEqual(stopped.returncode, 1, stopped.stdout)
            self.assertIn("T2", stopped.stderr)

    def test_strict_profile_gates_on_confidence_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state = json.loads(self.start(tmp_dir).read_text(encoding="utf-8"))

            self.assertEqual(state["stop_policy"], {"belief_threshold": 0.8, "severity": "error"})


if __name__ == "__main__":
    unittest.main()
