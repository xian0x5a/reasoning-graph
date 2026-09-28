import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from reasoning_graph.events import graph_digest


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
FIXTURES = PACKAGE_ROOT / "tests" / "fixtures"
STRICT_FIXTURE = FIXTURES / "valid" / "reasoning-graph-strict-good.json"
DUPLICATE_FIXTURE = FIXTURES / "invalid" / "audit" / "duplicate-report-candidate.json"


def stamp_graph_digest(state: dict) -> dict:
    """Give a hand-built state the digests the CLI writes, so a test reaches the check it targets."""
    for event in state.get("events", []):
        if event.get("action") in {"record", "refresh", "stop"}:
            event["graph_digest"] = graph_digest(state)
    return state


class DistinctCandidateCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )

    def test_audit_does_not_count_duplicate_report_rows(self) -> None:
        result = self.run_cli("audit", str(DUPLICATE_FIXTURE))

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("viable candidates 1 < stop_policy.min_viable_candidates 3", result.stderr)

    def test_audit_accepts_three_distinct_graph_candidates(self) -> None:
        state = json.loads(STRICT_FIXTURE.read_text(encoding="utf-8"))
        state["stop_policy"] = {
            "min_viable_candidates": 3,
            "severity": "error",
        }
        state["nodes"].extend([
            {"id": "CS2", "type": "candidate_solution", "text": "Candidate from A2", "answer_kind": "exact_answer", "prior": 0.4},
            {"id": "CS3", "type": "candidate_solution", "text": "Alternate from A1", "answer_kind": "exact_answer", "prior": 0.3},
        ])
        state["edges"].extend([
            {"id": "E3", "from": "A2", "to": "CS2", "type": "leads_to", "reasoning": "Candidate CS2 depends on A2."},
            {"id": "E4", "from": "CS2", "to": "G1", "type": "answers", "reasoning": "Candidate CS2 answers the goal."},
            {"id": "E5", "from": "A1", "to": "CS3", "type": "leads_to", "reasoning": "Candidate CS3 depends on A1."},
            {"id": "E6", "from": "CS3", "to": "G1", "type": "answers", "reasoning": "Candidate CS3 answers the goal."},
        ])

        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "distinct-candidates.json"
            state_path.write_text(json.dumps(stamp_graph_digest(state)), encoding="utf-8")
            result = self.run_cli("audit", str(state_path))

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
