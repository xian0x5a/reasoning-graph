"""Read-only inspection APIs must not mutate caller state (#9) and schema validation
must not depend on deprecated resolver APIs (#13)."""

import json
import sys
import unittest
import warnings
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PACKAGE_ROOT / "src"))

from reasoning_graph.audit import audit_state
from reasoning_graph.policy import best_candidate_ids, ranked_viable_candidates, sorted_report_candidates, strongest_grounded_candidate_belief
from reasoning_graph.schema_validation import patch_schema_errors, state_schema_errors
from reasoning_graph.validation import validate_state

FIXTURES = PACKAGE_ROOT / "tests" / "fixtures"


def load_fixture(*parts: str) -> dict:
    return json.loads((FIXTURES / Path(*parts)).read_text(encoding="utf-8"))


class ReadOnlyApiTests(unittest.TestCase):
    def test_audit_state_leaves_state_unchanged(self) -> None:
        state = load_fixture("valid", "reasoning-graph-strict-good.json")
        state.setdefault("report", {"candidates": [{"id": "CS1", "name": "Candidate"}]})
        before = json.dumps(state, sort_keys=True)

        result, _ = audit_state(state)
        validate_state(state)
        ranked_viable_candidates(state)
        best_candidate_ids(state)
        strongest_grounded_candidate_belief(state)
        sorted_report_candidates(state)

        self.assertTrue(result.ok, result.errors)
        self.assertEqual(json.dumps(state, sort_keys=True), before)


class SchemaResolverTests(unittest.TestCase):
    def test_schema_validation_emits_no_deprecation_warnings(self) -> None:
        patch = load_fixture("patches", "patch-with-factor-update.json")
        state = load_fixture("valid", "factors-state.json")

        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            self.assertEqual(patch_schema_errors(patch), [])
            self.assertEqual(state_schema_errors(state), [])

    def test_patch_schema_still_resolves_state_definitions(self) -> None:
        bad_patch = {"nodes": [{"id": "A1", "type": "not-a-type"}], "edges": [{"from": "A1", "to": "A1", "type": "supports"}]}

        errors = patch_schema_errors(bad_patch)

        self.assertTrue(any("$.nodes[0].type" in error for error in errors), errors)
        self.assertTrue(any("reasoning" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
