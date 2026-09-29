import json
import subprocess
import tempfile
import unittest
import warnings
from pathlib import Path

try:
    import jsonschema
except ImportError:  # pragma: no cover - optional developer dependency
    jsonschema = None


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
FIXTURES = PACKAGE_ROOT / "tests" / "fixtures"
VALID_FIXTURES = sorted((FIXTURES / "valid").glob("*.json"))
VALIDATE_INVALID_FIXTURES = {
    "removed-likelihood-ratio.json": "likelihood_ratio was removed; use score",
    "bad-node-type.json": "invalid type 'fact'",
    "candidate-missing-answers.json": "must connect to a goal with an answers edge",
    "direct-hypothesis-goal.json": "connects hypothesis H1 directly to goal G1",
    "invalid-stop-policy.json": "stop_policy.min_viable_candidates must be a non-negative integer",
    "overlapping-factors.json": "edge E2A1 is already grouped by F_SUPPORTS_A1",
}
AUDIT_INVALID_FIXTURES = {
    "duplicate-report-candidate.json": "viable candidates 1 < stop_policy.min_viable_candidates 3",
    "hypothesis-test-result.json": "test(s) without a recorded result observation: T1",
    "unanswered-accepted-goal.json": "accepted goal G2",
}
STATE_SCHEMA = PACKAGE_ROOT / "src" / "reasoning_graph" / "schemas" / "state.schema.json"
PATCH_SCHEMA = PACKAGE_ROOT / "src" / "reasoning_graph" / "schemas" / "patch.schema.json"


class ReasoningGraphFixtureTests(unittest.TestCase):
    def run_cli(self, *args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            **kwargs,
        )

    def test_installed_console_entrypoint_validates_fixture(self) -> None:
        try:
            result = subprocess.run(
                ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", "validate", str(FIXTURES / "valid" / "minimal-state.json")],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
            )
        except FileNotFoundError:
            self.skipTest("uv is not on PATH")
        if result.returncode == 127 or "No such file" in result.stderr:
            self.skipTest("uv is not on PATH")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok", result.stdout)

    def test_valid_fixture_matrix_validates(self) -> None:
        self.assertGreaterEqual(len(VALID_FIXTURES), 5)
        for fixture in VALID_FIXTURES:
            with self.subTest(fixture=fixture.name):
                result = self.run_cli("validate", str(fixture))
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("ok", result.stdout)

    def test_invalid_validate_fixture_matrix_fails_with_expected_errors(self) -> None:
        for fixture_name, expected in VALIDATE_INVALID_FIXTURES.items():
            with self.subTest(fixture=fixture_name):
                result = self.run_cli("validate", str(FIXTURES / "invalid" / "validate" / fixture_name))
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(expected, result.stderr)

    def test_invalid_audit_fixture_matrix_validates_then_fails_audit(self) -> None:
        for fixture_name, expected in AUDIT_INVALID_FIXTURES.items():
            fixture = FIXTURES / "invalid" / "audit" / fixture_name
            with self.subTest(fixture=fixture_name):
                valid = self.run_cli("validate", str(fixture))
                self.assertEqual(valid.returncode, 0, valid.stderr)
                audit = self.run_cli("audit", str(fixture))
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

    def test_cli_validate_rejects_a_frontier_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "legacy-frontier.json"
            state_path.write_text(
                json.dumps({
                    "nodes": [{"id": "G1", "type": "goal", "text": "Solve"}],
                    "edges": [],
                    "frontier": [{"id": "Q1", "node": "G1"}],
                }),
                encoding="utf-8",
            )
            result = self.run_cli("validate", str(state_path))
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("schema $", result.stderr)
            self.assertIn("{'required': ['frontier']}", result.stderr)

    @unittest.skipIf(jsonschema is None, "jsonschema not installed")
    def test_json_schemas_reject_known_legacy_fields(self) -> None:
        state_validator, patch_validator = self.schema_validators()
        modern_state = json.loads((FIXTURES / "valid" / "minimal-state.json").read_text(encoding="utf-8"))
        legacy_state_variants = {
            "solutions": {**modern_state, "solutions": ["CS1"]},
            "edge-label": {**modern_state, "edges": [{"from": "G1", "to": "G1", "label": "supports"}]},
            "frontier": {**modern_state, "frontier": []},
            "search-policy": {**modern_state, "search_policy": {}},
            "event-pop-action": {**modern_state, "events": [{"step": 1, "action": "pop", "item": "Q1", "cost": 0}]},
            "premise-groups": {**modern_state, "premise_groups": []},
            "event-solution-action": {**modern_state, "events": [{"step": 1, "action": "solution", "item": "Q1", "node": "CS1", "cost": 0}]},
            "event-update-premise-groups": {**modern_state, "events": [{"step": 1, "action": "record", "reason": "r", "add_nodes": [], "add_edges": [], "update_premise_groups": ["PG1"]}]},
            "event-add-factors": {**modern_state, "events": [{"step": 1, "action": "record", "reason": "r", "add_nodes": [], "add_edges": [], "add_factors": ["F1"]}]},
        }
        for name, state in legacy_state_variants.items():
            with self.subTest(state=name), self.assertRaises(jsonschema.ValidationError):
                state_validator.validate(state)

        modern_patch = {"nodes": [], "edges": [], "frontier": []}
        legacy_patch_variants = {
            "add-node-objects": {**modern_patch, "add_node_objects": []},
            "solution": {**modern_patch, "solution": "CS1"},
            "solution-node": {**modern_patch, "solution_node": "CS1"},
            "premise-groups": {**modern_patch, "premise_groups": []},
            "update-premise-groups": {**modern_patch, "update_premise_groups": []},
            "no-reopen-reason": {**modern_patch, "no_reopen_reason": "legacy"},
            "under-branching-reason": {**modern_patch, "under_branching_reason": "legacy"},
            "existing-sibling-frontier": {**modern_patch, "existing_sibling_frontier": ["Q1"]},
            "frontier": {**modern_patch, "frontier": []},
            "no-new-work-reason": {**modern_patch, "no_new_work_reason": "legacy"},
            "stop-alias": {**modern_patch, "stop": "legacy stop", "outcome": "user_stopped"},
        }
        for name, patch in legacy_patch_variants.items():
            with self.subTest(patch=name), self.assertRaises(jsonschema.ValidationError):
                patch_validator.validate(patch)

    def test_golden_cli_outputs_stay_stable(self) -> None:
        commands = {
            "init-strict.json": ("init", "--goal", "Solve the problem", "--strict"),
            "doctor-strict-driver.txt": ("doctor", str(FIXTURES / "valid" / "strict-driver-state.json")),
        }
        for golden_name, args in commands.items():
            with self.subTest(golden=golden_name):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
                golden = (FIXTURES / "golden" / golden_name).read_text(encoding="utf-8")
                self.assertEqual(result.stdout, golden)

    def test_patch_fixtures_apply_as_records(self) -> None:
        base_state = {
            "nodes": [
                {"id": "G1", "type": "goal", "text": "Find exact answer"},
                {"id": "A1", "type": "hypothesis", "text": "Primary route", "score": 3},
            ],
            "edges": [],
        }
        for patch in sorted((FIXTURES / "patches").glob("*.json")):
            with self.subTest(patch=patch.name), tempfile.TemporaryDirectory() as tmp_dir:
                state_path = Path(tmp_dir) / "state.json"
                state_path.write_text(json.dumps(base_state), encoding="utf-8")
                recorded = self.run_cli("record", str(state_path), "--patch", str(patch))
                self.assertEqual(recorded.returncode, 0, recorded.stderr)
                valid = self.run_cli("validate", str(state_path))
                self.assertEqual(valid.returncode, 0, valid.stderr)


if __name__ == "__main__":
    unittest.main()
