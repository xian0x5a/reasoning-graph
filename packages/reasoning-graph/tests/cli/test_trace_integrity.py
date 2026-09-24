"""Forced commands cannot create invalid traces (#19) and audit rejects forged or
repeated event claims (#20)."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
FIXTURE = PACKAGE_ROOT / "tests" / "fixtures" / "valid" / "reasoning-graph-strict-good.json"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )


def fresh_state() -> dict:
    return {
        "nodes": [
            {"id": "G1", "type": "goal", "text": "Find the exact answer"},
            {"id": "A1", "type": "assumption", "text": "Likely route", "prior": 0.6},
            {"id": "A2", "type": "assumption", "text": "Other route", "prior": 0.4},
            {"id": "CS1", "type": "candidate_solution", "text": "Answer one", "answer_kind": "exact_answer", "prior": 0.5},
        ],
        "edges": [
            {"id": "CS1-G1", "from": "CS1", "to": "G1", "type": "answers", "reasoning": "The candidate supplies the requested answer."},
        ],
        "frontier": [
            {"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}},
            {"id": "Q2", "node": "A2", "cost_components": {"truth": "auto"}},
        ],
    }


class ForcedCommandTests(unittest.TestCase):
    def write_state(self, tmp_dir: str, state: dict) -> Path:
        path = Path(tmp_dir) / "state.json"
        path.write_text(json.dumps(state), encoding="utf-8")
        return path

    def test_forced_expand_requires_existing_frontier_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.write_state(tmp_dir, fresh_state())
            self.assertEqual(run_cli("next", str(state_path), "--pop").returncode, 0)
            before = state_path.read_text(encoding="utf-8")
            patch_path = Path(tmp_dir) / "patch.json"
            patch_path.write_text(json.dumps({"no_new_work_reason": "nothing"}), encoding="utf-8")

            result = run_cli("expand", str(state_path), "--item", "Q9", "--patch", str(patch_path), "--force")

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("frontier item not found: Q9", result.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_forced_expand_and_assign_reject_uninitialized_driver(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.write_state(tmp_dir, fresh_state())
            before = state_path.read_text(encoding="utf-8")
            patch_path = Path(tmp_dir) / "patch.json"
            patch_path.write_text(json.dumps({"no_new_work_reason": "nothing"}), encoding="utf-8")

            expanded = run_cli("expand", str(state_path), "--item", "Q1", "--patch", str(patch_path), "--force")
            assigned = run_cli("assign", str(state_path), "--item", "Q1", "--force")

            for result in (expanded, assigned):
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("before driver init", result.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_forced_expand_requires_popped_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.write_state(tmp_dir, fresh_state())
            self.assertEqual(run_cli("next", str(state_path), "--pop").returncode, 0)
            patch_path = Path(tmp_dir) / "patch.json"
            patch_path.write_text(json.dumps({"no_new_work_reason": "nothing"}), encoding="utf-8")

            result = run_cli("expand", str(state_path), "--item", "Q2", "--patch", str(patch_path), "--force")

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("Q2 has not been popped", result.stderr)

    def test_rank_rejects_uninitialized_driver(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.write_state(tmp_dir, fresh_state())
            before = state_path.read_text(encoding="utf-8")

            result = run_cli("rank", str(state_path))

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("before driver init", result.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)


class AuditEventIntegrityTests(unittest.TestCase):
    def audit(self, state: dict) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            return run_cli("audit", str(state_path))

    def test_repeated_add_claims_are_rejected(self) -> None:
        for field, expected in (
            ("add_nodes", "node CS1 was already added by events[2]"),
            ("add_edges", "edge E1 was already added by events[2]"),
            ("add_frontier", "frontier item Q3 was already added by events[2]"),
        ):
            with self.subTest(field=field):
                state = json.loads(FIXTURE.read_text(encoding="utf-8"))
                state["events"][2][field] = state["events"][2][field] * 2
                result = self.audit(state)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(expected, result.stderr)

    def test_forged_rank_payloads_are_rejected(self) -> None:
        forged = {
            "belief": lambda event: event.update({"belief": 0.99}),
            "row-belief": lambda event: event["candidates"][0].update({"belief": 0.99}),
            "row-node": lambda event: event["candidates"][0].update({"node": "A1"}),
            "extra-row": lambda event: event["candidates"].append({"node": "CS1", "belief": 0.6, "effective_truth_cost": 0.510826}),
        }
        for label, mutate in forged.items():
            with self.subTest(forged=label):
                state = json.loads(FIXTURE.read_text(encoding="utf-8"))
                mutate(state["events"][4])
                result = self.audit(state)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("events[4] step=5 action=rank", result.stderr)
                self.assertIn("derived", result.stderr)

    def test_rank_events_are_checked_against_graph_at_rank_time(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            patch_path = Path(tmp_dir) / "patch.json"
            state_path.write_text(json.dumps(fresh_state()), encoding="utf-8")

            # Pop A1, close it by ranking CS1 (belief 0.5), then pop A2 and add a stronger CS2.
            self.assertEqual(run_cli("next", str(state_path), "--pop").returncode, 0)
            self.assertEqual(run_cli("rank", str(state_path)).returncode, 0)
            self.assertEqual(run_cli("next", str(state_path), "--pop").returncode, 0)
            patch_path.write_text(
                json.dumps({
                    "nodes": [{"id": "CS2", "type": "candidate_solution", "text": "Answer two", "answer_kind": "exact_answer", "prior": 0.9}],
                    "edges": [
                        {"id": "A2-CS2", "from": "A2", "to": "CS2", "type": "leads_to", "reasoning": "The other route yields answer two."},
                        {"id": "CS2-G1", "from": "CS2", "to": "G1", "type": "answers", "reasoning": "Answer two answers the goal."},
                    ],
                    "no_new_work_reason": "Candidate recorded; no further work on this route.",
                }),
                encoding="utf-8",
            )
            self.assertEqual(run_cli("expand", str(state_path), "--item", "Q2", "--patch", str(patch_path)).returncode, 0)
            stopped = run_cli("stop", str(state_path), "--reason", "manual stop", "--outcome", "user_stopped")
            self.assertEqual(stopped.returncode, 0, stopped.stderr)

            state = json.loads(state_path.read_text(encoding="utf-8"))
            rank_event = next(event for event in state["events"] if event["action"] == "rank")
            self.assertEqual(rank_event["best"], "CS1")
            audit = run_cli("audit", str(state_path))
            self.assertEqual(audit.returncode, 0, audit.stderr)


if __name__ == "__main__":
    unittest.main()
