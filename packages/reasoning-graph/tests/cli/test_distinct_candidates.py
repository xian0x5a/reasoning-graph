import json
import subprocess
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
FIXTURES = PACKAGE_ROOT / "tests" / "fixtures"
STRICT_FIXTURE = FIXTURES / "valid" / "reasoning-graph-strict-good.json"
DUPLICATE_FIXTURE = FIXTURES / "invalid" / "audit" / "duplicate-report-candidate.json"


class DistinctCandidateCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
        )

    def test_stop_review_does_not_count_duplicate_report_rows(self) -> None:
        result = self.run_cli("stop-review", str(DUPLICATE_FIXTURE))

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("viable_candidates=1 < min_viable_candidates=3", result.stdout)

    def test_audit_accepts_three_distinct_graph_candidates(self) -> None:
        state = json.loads(STRICT_FIXTURE.read_text(encoding="utf-8"))
        state["stop_policy"] = {
            "min_viable_candidates": 3,
            "max_live_frontier_items": 0,
            "severity": "error",
        }
        state["nodes"].extend([
            {"id": "CS2", "type": "candidate_solution", "text": "Candidate from A2", "answer_kind": "exact_answer", "prior": 0.4},
            {"id": "CS3", "type": "candidate_solution", "text": "Alternate from A1", "answer_kind": "exact_answer", "prior": 0.3},
        ])
        state["edges"].extend([
            {"id": "E3", "from": "A2", "to": "CS2", "type": "leads_to"},
            {"id": "E4", "from": "CS2", "to": "G1", "type": "answers"},
            {"id": "E5", "from": "A1", "to": "CS3", "type": "leads_to"},
            {"id": "E6", "from": "CS3", "to": "G1", "type": "answers"},
        ])

        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "distinct-candidates.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            result = self.run_cli("audit", str(state_path))

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
