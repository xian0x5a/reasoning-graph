import json
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

try:
    import jsonschema
except ImportError:  # pragma: no cover - optional developer dependency
    jsonschema = None


REPO_ROOT = Path(__file__).resolve().parents[2]
RG = REPO_ROOT / "skills" / "reasoning-graph" / "scripts" / "rg.py"
FIXTURES = REPO_ROOT / "tests" / "fixtures"
VALID_FIXTURES = sorted((FIXTURES / "valid").glob("*.json"))
VALIDATE_INVALID_FIXTURES = {
    "bad-likelihood-direction.json": "supports likelihood ratio must be > 1",
    "bad-node-type.json": "invalid type 'fact'",
    "candidate-missing-answers.json": "must connect to a goal with an answers edge",
    "direct-assumption-goal.json": "connects assumption A1 directly to goal G1",
    "invalid-stop-policy.json": "stop_policy.max_live_frontier_items must be a non-negative integer",
    "overlapping-factors.json": "supports factors for target 'A1' overlap",
}
AUDIT_INVALID_FIXTURES = {
    "lazy-epistemic-stop.json": "stop_policy requires frontier exhaustion for epistemic stop",
    "pending-pop-not-expanded.json": "stop cannot follow unresolved popped item Q1",
}
STATE_SCHEMA = REPO_ROOT / "skills" / "reasoning-graph" / "schemas" / "state.schema.json"
PATCH_SCHEMA = REPO_ROOT / "skills" / "reasoning-graph" / "schemas" / "patch.schema.json"


class ReasoningGraphFixtureTests(unittest.TestCase):
    def run_rg(self, *args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(RG), *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            **kwargs,
        )

    def test_valid_fixture_matrix_validates(self) -> None:
        self.assertGreaterEqual(len(VALID_FIXTURES), 5)
        for fixture in VALID_FIXTURES:
            with self.subTest(fixture=fixture.name):
                result = self.run_rg("validate", str(fixture))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("ok", result.stdout)

    def test_invalid_validate_fixture_matrix_fails_with_expected_errors(self) -> None:
        for fixture_name, expected in VALIDATE_INVALID_FIXTURES.items():
            with self.subTest(fixture=fixture_name):
                result = self.run_rg("validate", str(FIXTURES / "invalid" / "validate" / fixture_name))
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(expected, result.stderr)

    def test_invalid_audit_fixture_matrix_validates_then_fails_audit(self) -> None:
        for fixture_name, expected in AUDIT_INVALID_FIXTURES.items():
            fixture = FIXTURES / "invalid" / "audit" / fixture_name
            with self.subTest(fixture=fixture_name):
                valid = self.run_rg("validate", str(fixture))
                self.assertEqual(valid.returncode, 0, valid.stderr)
                audit = self.run_rg("audit", str(fixture))
                self.assertNotEqual(audit.returncode, 0, audit.stdout)
                self.assertIn(expected, audit.stderr)

    def schema_validators(self) -> tuple[object, object]:
        state_schema = json.loads(STATE_SCHEMA.read_text(encoding="utf-8"))
        patch_schema = json.loads(PATCH_SCHEMA.read_text(encoding="utf-8"))
        state_validator = jsonschema.Draft202012Validator(state_schema)
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            resolver = jsonschema.RefResolver.from_schema(
                patch_schema,
                store={state_schema["$id"]: state_schema, "state.schema.json": state_schema},
            )
            patch_validator = jsonschema.Draft202012Validator(patch_schema, resolver=resolver)
        return state_validator, patch_validator

    @unittest.skipIf(jsonschema is None, "jsonschema not installed")
    def test_state_and_patch_fixtures_match_json_schemas(self) -> None:
        state_validator, patch_validator = self.schema_validators()

        for fixture in VALID_FIXTURES:
            with self.subTest(state=fixture.name):
                state_validator.validate(json.loads(fixture.read_text(encoding="utf-8")))
        for fixture in sorted((FIXTURES / "patches").glob("*.json")):
            with self.subTest(patch=fixture.name):
                patch_validator.validate(json.loads(fixture.read_text(encoding="utf-8")))

    @unittest.skipIf(jsonschema is None, "jsonschema not installed")
    def test_json_schemas_reject_known_legacy_fields(self) -> None:
        state_validator, patch_validator = self.schema_validators()
        modern_state = json.loads((FIXTURES / "valid" / "minimal-state.json").read_text(encoding="utf-8"))
        legacy_state_variants = {
            "solutions": {**modern_state, "solutions": ["CS1"]},
            "edge-label": {**modern_state, "edges": [{"from": "G1", "to": "G1", "label": "supports"}]},
            "frontier-path-cost": {**modern_state, "frontier": [{"id": "Q1", "node": "G1", "path_cost": 1.0}]},
            "event-solution-action": {**modern_state, "events": [{"step": 1, "action": "solution", "item": "Q1", "node": "CS1", "cost": 0}]},
            "event-add-factors": {**modern_state, "events": [{"step": 1, "action": "expand", "item": "Q1", "add_nodes": [], "add_edges": [], "add_frontier": [], "add_factors": ["F1"]}]},
        }
        for name, state in legacy_state_variants.items():
            with self.subTest(state=name), self.assertRaises(jsonschema.ValidationError):
                state_validator.validate(state)

        modern_patch = {"nodes": [], "edges": [], "frontier": []}
        legacy_patch_variants = {
            "add-node-objects": {**modern_patch, "add_node_objects": []},
            "solution": {**modern_patch, "solution": "CS1"},
            "solution-node": {**modern_patch, "solution_node": "CS1"},
            "no-reopen-reason": {**modern_patch, "no_reopen_reason": "legacy"},
            "stop-alias": {**modern_patch, "stop": "legacy stop", "outcome": "user_stopped"},
        }
        for name, patch in legacy_patch_variants.items():
            with self.subTest(patch=name), self.assertRaises(jsonschema.ValidationError):
                patch_validator.validate(patch)

    def test_golden_cli_outputs_stay_stable(self) -> None:
        commands = {
            "template-strict.json": ("template", "strict"),
            "template-benchmark.json": ("template", "benchmark"),
            "doctor-strict-driver.txt": ("doctor", str(FIXTURES / "valid" / "strict-driver-state.json")),
            "stop-review-pass.txt": ("stop-review", str(FIXTURES / "valid" / "stopped-reviewed-state.json")),
        }
        for golden_name, args in commands.items():
            with self.subTest(golden=golden_name):
                result = self.run_rg(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                golden = (FIXTURES / "golden" / golden_name).read_text(encoding="utf-8")
                self.assertEqual(result.stdout, golden)

    def test_patch_fixtures_apply_to_popped_branch(self) -> None:
        base_state = {
            "nodes": [
                {"id": "G1", "type": "goal", "text": "Find exact answer"},
                {"id": "A1", "type": "assumption", "text": "Primary route", "prior": 0.6},
            ],
            "edges": [],
            "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
        }
        for patch in sorted((FIXTURES / "patches").glob("*.json")):
            with self.subTest(patch=patch.name), tempfile.TemporaryDirectory() as tmp_dir:
                state_path = Path(tmp_dir) / "state.json"
                state_path.write_text(json.dumps(base_state), encoding="utf-8")
                popped = self.run_rg("next", str(state_path), "--pop", "-i")
                self.assertEqual(popped.returncode, 0, popped.stderr)
                expanded = self.run_rg("expand", str(state_path), "--item", "Q1", "--patch", str(patch), "-i")
                self.assertEqual(expanded.returncode, 0, expanded.stderr)
                valid = self.run_rg("validate", str(state_path))
                self.assertEqual(valid.returncode, 0, valid.stderr)


if __name__ == "__main__":
    unittest.main()
