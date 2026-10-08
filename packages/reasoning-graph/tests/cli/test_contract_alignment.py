"""Candidate answer_kind and patch field contracts."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
FIXTURES = PACKAGE_ROOT / "tests" / "fixtures"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )


def base_state() -> dict:
    return {
        "nodes": [
            {"id": "G1", "type": "goal", "text": "Find the exact answer"},
            {"id": "A1", "type": "hypothesis", "text": "Likely route", "score": 3},
            {"id": "A2", "type": "hypothesis", "text": "Other route", "score": 2},
            {"id": "CS1", "type": "candidate_solution", "text": "Answer one", "answer_kind": "exact_answer", "score": 3},
        ],
        "edges": [
            {"from": "A1", "to": "CS1", "type": "leads_to"},
            {"from": "CS1", "to": "G1", "type": "answers"},
        ],
    }


class ContractAlignmentTests(unittest.TestCase):
    def validate(self, state: dict) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            return run_cli("audit", str(state_path))

    def record(self, patch: dict) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            patch_path = Path(tmp_dir) / "patch.json"
            state_path.write_text(json.dumps(base_state()), encoding="utf-8")
            patch_path.write_text(json.dumps(patch), encoding="utf-8")
            return run_cli("record", str(state_path), "--patch", str(patch_path))

    # --- answer_kind ---

    def test_candidate_without_answer_kind_is_rejected(self) -> None:
        state = base_state()
        del state["nodes"][3]["answer_kind"]
        result = self.validate(state)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("answer_kind", result.stderr)

        patched = self.record({
            "nodes": [{"id": "CS2", "type": "candidate_solution", "text": "Answer two", "score": 2}],
            "edges": [{"from": "CS2", "to": "G1", "type": "answers"}],
        })
        self.assertEqual(patched.returncode, 1, patched.stdout)
        self.assertIn("answer_kind", patched.stderr)

    # --- patch fields ---

    def test_patch_rejects_unimplemented_or_ambiguous_fields(self) -> None:
        factor = {"id": "F1", "edges": ["A1-A2", "A2-CS1"], "score": 4, "note": "Shared source."}
        rejected_patches = {
            "outcome-alias": {"stop_reason": "done", "stop_outcome": "user_stopped", "outcome": "solved"},
            "factors-and-update-factors": {"factors": [factor], "update_factors": [factor]},
            "decorative-updated-nodes": {"updated_nodes": [{"id": "A1", "fields": ["score"]}]},
            "unknown-field": {"notes": "free text"},
        }
        for label, patch in rejected_patches.items():
            with self.subTest(patch=label):
                result = self.record(patch)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("error: schema $", result.stderr)


if __name__ == "__main__":
    unittest.main()
