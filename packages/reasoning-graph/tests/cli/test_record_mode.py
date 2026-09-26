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
                {"id": "O1", "type": "observation", "text": "Probe output", "source": "probe.log", "quote": "exit 3", "note": "Only the last run was logged", "prior": observation_prior},
            ],
            "edges": [edge("T1", "O1", "leads_to")],
        }))
        self.ok(self.record(state_path, {
            "reason": "Concluded from the probe",
            "nodes": [{"id": "CS1", "type": "candidate_solution", "text": "Root cause", "answer_kind": "exact_answer"}],
            "edges": [edge("O1", "CS1", "leads_to"), edge("CS1", "G1", "answers")],
        }))

    def review(self, state_path: Path, verdict: str = "pass", findings: str = "Observations match their quotes.") -> subprocess.CompletedProcess[str]:
        return run_cli("review", str(state_path), "--reviewer", "reviewer-1", "--verdict", verdict, "--findings", findings)

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
            live_view = state_path.with_suffix(".html").read_text(encoding="utf-8")
            self.assertIn("CS1", live_view)
            self.assertIn("exit 3", live_view)
            self.assertIn("Only the last run was logged", live_view)

    def test_doctor_accepts_a_working_state_and_audits_only_once_stopped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 0.95)

            working = run_cli("doctor", str(state_path))
            self.ok(working)
            self.assertIn("audit skipped (not stopped)", working.stdout)

            self.ok(self.review(state_path))
            self.ok(self.stop(state_path))
            stopped = run_cli("doctor", str(state_path))
            self.ok(stopped)
            self.assertIn("doctor: audit ok", stopped.stdout)

    def test_record_writes_computed_belief_on_each_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 0.95)

            nodes = {node["id"]: node for node in json.loads(state_path.read_text(encoding="utf-8"))["nodes"]}
            computed = json.loads(run_cli("beliefs", str(state_path), "--json").stdout)

            self.assertEqual({row["id"]: nodes[row["id"]]["belief"] for row in computed}, {row["id"]: row["belief"] for row in computed})
            self.assertEqual(nodes["O1"]["belief"], 0.95)
            self.assertNotIn("belief", nodes["G1"])
            self.assertNotIn("belief", nodes["T1"])

    def test_record_rejects_an_authored_belief(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 0.95)

            new_node = self.record(state_path, {"reason": "r", "nodes": [{"id": "H1", "type": "hypothesis", "text": "Guess", "prior": 0.5, "belief": 0.9}]})
            update = self.record(state_path, {"reason": "r", "update_nodes": [{"id": "O1", "set": {"belief": 0.99}}]})

            for rejected in (new_node, update):
                self.assertEqual(rejected.returncode, 1, rejected.stdout)
                self.assertIn("belief", rejected.stderr)

    def test_stale_belief_fails_validation_until_refreshed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 0.95)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            next(node for node in state["nodes"] if node["id"] == "O1")["prior"] = 0.6
            state_path.write_text(json.dumps(state), encoding="utf-8")

            stale = run_cli("validate", str(state_path))
            self.ok(run_cli("beliefs", str(state_path), "--write"))
            refreshed = json.loads(state_path.read_text(encoding="utf-8"))

            self.assertEqual(stale.returncode, 1, stale.stdout)
            self.assertIn("stale belief", stale.stderr)
            self.assertIn("beliefs", stale.stderr)
            self.ok(run_cli("validate", str(state_path)))
            self.assertEqual(next(node for node in refreshed["nodes"] if node["id"] == "O1")["belief"], 0.6)

    def test_belief_is_only_written_on_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["nodes"][0]["belief"] = 1.0
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = run_cli("validate", str(state_path))

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("G1", result.stderr)

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
            self.ok(self.review(state_path))

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

    def test_strict_profile_gates_on_confidence_and_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state = json.loads(self.start(tmp_dir).read_text(encoding="utf-8"))

            self.assertEqual(state["stop_policy"], {"belief_threshold": 0.8, "require_review": True, "severity": "error"})

    def test_solved_stop_needs_a_passing_review_of_the_final_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 0.95)

            unreviewed = self.stop(state_path)
            self.ok(self.review(state_path, "fail", "O1 overstates its quote"))
            failed_review = self.stop(state_path)
            self.ok(self.review(state_path))
            self.ok(self.record(state_path, {"reason": "Late addition", "nodes": [{"id": "O2", "type": "observation", "text": "Late log", "source": "probe.log", "prior": 0.9}]}))
            stale_review = self.stop(state_path)

            for stopped in (unreviewed, failed_review, stale_review):
                self.assertEqual(stopped.returncode, 1, stopped.stdout)
                self.assertIn("review", stopped.stderr)
            self.ok(self.review(state_path))
            self.ok(self.stop(state_path))

    def test_review_needs_reviewer_and_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 0.95)

            no_findings = run_cli("review", str(state_path), "--reviewer", "reviewer-1", "--verdict", "fail", "--findings", " ")
            no_reviewer = run_cli("review", str(state_path), "--reviewer", " ", "--verdict", "pass", "--findings", "ok")

            self.assertEqual(no_findings.returncode, 1)
            self.assertEqual(no_reviewer.returncode, 1)


if __name__ == "__main__":
    unittest.main()
