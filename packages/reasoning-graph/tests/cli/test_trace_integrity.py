"""Audit rejects forged or repeated event claims (#20)."""

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


class AuditEventIntegrityTests(unittest.TestCase):
    def audit(self, state: dict) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            return run_cli("audit", str(state_path))

    def test_repeated_add_claims_are_rejected(self) -> None:
        for field, expected in (
            ("add_nodes", "node CS1 was already added by events[0]"),
            ("add_edges", "edge E1 was already added by events[0]"),
        ):
            with self.subTest(field=field):
                state = json.loads(FIXTURE.read_text(encoding="utf-8"))
                state["events"][0][field] = state["events"][0][field] * 2
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
                mutate(state["events"][1])
                result = self.audit(state)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("events[1] step=2 action=rank", result.stderr)
                self.assertIn("derived", result.stderr)


if __name__ == "__main__":
    unittest.main()
