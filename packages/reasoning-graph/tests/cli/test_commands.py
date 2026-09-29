import json
import math
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from typing import Any

try:
    import jsonschema
except ImportError:  # pragma: no cover - optional developer dependency
    jsonschema = None


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
PACKAGE_SRC_ROOT = PACKAGE_ROOT / "src"
sys.path.insert(0, str(PACKAGE_SRC_ROOT))

from reasoning_graph.costs import node_effective_truth_costs


FIXTURE = PACKAGE_ROOT / "tests" / "fixtures" / "valid" / "reasoning-graph-strict-good.json"
STATE_SCHEMA = PACKAGE_SRC_ROOT / "reasoning_graph" / "schemas" / "state.schema.json"
PATCH_SCHEMA = PACKAGE_SRC_ROOT / "reasoning_graph" / "schemas" / "patch.schema.json"

# A valid record patch against the fixture: one new observation supporting A1.
FIXTURE_RECORD_PATCH = {
    "nodes": [{"id": "O2", "type": "observation", "text": "Second symptom report", "score": 5}],
    "edges": [{"from": "O2", "to": "A1", "type": "supports", "score": 3}],
}


def truth_cost(state: dict[str, Any], node_id: str) -> float:
    return node_effective_truth_costs(state)[node_id]


class ReasoningGraphCliBasicTests(unittest.TestCase):
    def test_repository_layout_keeps_skill_docs_only_and_package_separate(self) -> None:
        self.assertTrue((PACKAGE_ROOT / "pyproject.toml").is_file())
        self.assertTrue((PACKAGE_ROOT / "src" / "reasoning_graph").is_dir())
        self.assertTrue((PACKAGE_ROOT / "tests" / "cli").is_dir())
        skill_root = REPO_ROOT / "skills" / "reasoning-graph"
        self.assertTrue((skill_root / "SKILL.md").is_file())
        self.assertTrue((skill_root / "docs").is_dir())
        self.assertTrue((skill_root / ".dotman-skip").is_file())
        self.assertFalse((skill_root / "src").exists())
        self.assertFalse((skill_root / "pyproject.toml").exists())
        self.assertFalse((skill_root / "uv.lock").exists())
        self.assertFalse((skill_root / "bin").exists())

    def run_cli(self, *args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            **kwargs,
        )

    def write_fixture(self, tmp_dir: str) -> tuple[Path, Path, str]:
        """Write the fixture state and the sample record patch; return (state, patch, original text)."""
        state_path = Path(tmp_dir) / "state.json"
        patch_path = Path(tmp_dir) / "patch.json"
        original = FIXTURE.read_text(encoding="utf-8")
        state_path.write_text(original, encoding="utf-8")
        patch_path.write_text(json.dumps(FIXTURE_RECORD_PATCH), encoding="utf-8")
        return state_path, patch_path, original

    def test_json_schemas_parse_and_cover_core_enums(self) -> None:
        state_schema = json.loads(STATE_SCHEMA.read_text(encoding="utf-8"))
        patch_schema = json.loads(PATCH_SCHEMA.read_text(encoding="utf-8"))

        self.assertEqual(state_schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertIn("candidate_solution", state_schema["$defs"]["node"]["properties"]["type"]["enum"])
        self.assertIn("answers", state_schema["$defs"]["edge"]["properties"]["type"]["enum"])
        self.assertNotIn("event", state_schema["$defs"])
        self.assertNotIn("stop_policy", state_schema["properties"])
        self.assertIn("answer", patch_schema["properties"])
        self.assertIn("exact_answer", state_schema["$defs"]["node"]["properties"]["answer_kind"]["enum"])
        self.assertNotIn("reason", patch_schema["properties"])
        self.assertNotIn("events", state_schema["properties"])
        serialized_schemas = json.dumps({"state": state_schema, "patch": patch_schema})
        self.assertNotIn('"deprecated"', serialized_schemas)
        self.assertNotIn('"solutions"', state_schema["properties"])
        self.assertNotIn("frontier", state_schema["properties"])
        self.assertNotIn('"label"', state_schema["$defs"]["edge"]["properties"])
        self.assertNotIn("frontier", patch_schema["properties"])
        self.assertNotIn("stop_outcome", patch_schema["properties"])
        self.assertNotIn('"solution_node"', patch_schema["properties"])
        self.assertNotIn('"no_reopen_reason"', patch_schema["properties"])

    def test_schema_command_emits_packaged_schema_json(self) -> None:
        result = self.run_cli("schema", "state")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), json.loads(STATE_SCHEMA.read_text(encoding="utf-8")))

    @unittest.skipIf(jsonschema is None, "jsonschema not installed")
    def test_emitted_patch_schema_validates_standalone(self) -> None:
        result = self.run_cli("schema", "patch")

        self.assertEqual(result.returncode, 0, result.stderr)
        emitted_schema = json.loads(result.stdout)
        patch = {
            "nodes": [
                {"score": 3, "id": "A1", "type": "hypothesis", "text": "First"},
                {"score": 3, "id": "A2", "type": "hypothesis", "text": "Second"},
            ],
            "edges": [{"from": "A1", "to": "A2", "type": "supports"}],
            "factors": [{"id": "F1", "edges": ["A1-A2", "E2"], "score": 3, "note": "Both rest on one reading."}],
        }

        jsonschema.Draft202012Validator(emitted_schema).validate(patch)

    def test_schema_command_writes_patch_schema_to_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "patch.schema.json"

            result = self.run_cli("schema", "patch", "-o", str(output_path))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            emitted_schema = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(emitted_schema["properties"]["nodes"]["items"]["$ref"], "#/$defs/state/node")
            self.assertIn("state", emitted_schema["$defs"])

    def test_mutating_commands_rewrite_state_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path, patch_path, _ = self.write_fixture(tmp_dir)

            result = self.run_cli("record", str(state_path), "--patch", str(patch_path))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertIn("O2", {node["id"] for node in state["nodes"]})

    def test_output_path_overrides_default_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path, patch_path, original = self.write_fixture(tmp_dir)
            output_path = Path(tmp_dir) / "recorded.json"

            result = self.run_cli("record", str(state_path), "--patch", str(patch_path), "-o", str(output_path))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original)
            recorded = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertIn("O2", {node["id"] for node in recorded["nodes"]})

    def test_output_dash_emits_stdout_without_mutating_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path, patch_path, original = self.write_fixture(tmp_dir)

            result = self.run_cli("record", str(state_path), "--patch", str(patch_path), "-o", "-")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original)
            state = json.loads(result.stdout)
            self.assertIn("O2", {node["id"] for node in state["nodes"]})

    def test_record_stdin_emits_mutated_state_to_stdout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            patch_path = Path(tmp_dir) / "patch.json"
            patch_path.write_text(json.dumps(FIXTURE_RECORD_PATCH), encoding="utf-8")

            result = self.run_cli("record", "-", "--patch", str(patch_path), input=FIXTURE.read_text(encoding="utf-8"))

        self.assertEqual(result.returncode, 0, result.stderr)
        persisted = json.loads(result.stdout)
        self.assertIn("O2", {node["id"] for node in persisted["nodes"]})

    def test_text_output_dash_emits_stdout(self) -> None:
        result = self.run_cli("mermaid", str(FIXTURE), "-o", "-")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("flowchart", result.stdout)

    @unittest.skipIf(jsonschema is None, "jsonschema not installed")
    def test_json_schema_validates_fixture_and_patch_examples(self) -> None:
        state_schema = json.loads(STATE_SCHEMA.read_text(encoding="utf-8"))
        patch_schema = json.loads(PATCH_SCHEMA.read_text(encoding="utf-8"))
        fixture_state = json.loads(FIXTURE.read_text(encoding="utf-8"))
        patch = {
            "nodes": [{"id": "A3", "type": "hypothesis", "text": "Third cause", "score": 1}],
            "update_nodes": [{"id": "A1", "set": {"score": 4}}],
            "edges": [{"from": "A3", "to": "CS1", "type": "supports"}],
        }

        state_validator = jsonschema.Draft202012Validator(state_schema)
        state_validator.validate(fixture_state)
        with self.assertRaises(jsonschema.ValidationError):
            state_validator.validate({"nodes": [{"id": "X1", "type": "fact"}]})

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            resolver = jsonschema.RefResolver.from_schema(
                patch_schema,
                store={
                    state_schema["$id"]: state_schema,
                    "state.schema.json": state_schema,
                },
            )
            patch_validator = jsonschema.Draft202012Validator(patch_schema, resolver=resolver)
        patch_validator.validate(patch)
        with self.assertRaises(jsonschema.ValidationError):
            patch_validator.validate({"stop_reason": "done", "stop_outcome": "solved"})

        with self.assertRaises(jsonschema.ValidationError):
            patch_validator.validate({"update_nodes": [{"id": "A1", "set": {"id": "A2"}}]})

    def test_record_patch_updates_existing_node_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            patch_path = Path(tmp_dir) / "patch.json"
            state_path.write_text(
                json.dumps({
                    "nodes": [{"id": "A1", "type": "hypothesis", "text": "Likely cause", "score": 1}],
                    "edges": [],
                }),
                encoding="utf-8",
            )
            patch_path.write_text(
                json.dumps({
                    "update_nodes": [{"id": "A1", "set": {"score": 4, "exhausted": True, "exhaustion_reason": "cheap checks complete"}}],
                }),
                encoding="utf-8",
            )

            recorded = self.run_cli("record", str(state_path), "--patch", str(patch_path))
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            updated = json.loads(state_path.read_text(encoding="utf-8"))

            self.assertEqual(updated["nodes"][0]["score"], 4)
            self.assertTrue(updated["nodes"][0]["exhausted"])
            self.assertEqual(updated["nodes"][0]["exhaustion_reason"], "cheap checks complete")

    def test_record_patch_rejects_missing_or_identity_node_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            patch_path = Path(tmp_dir) / "patch.json"
            state_path.write_text(
                json.dumps({
                    "nodes": [{"id": "A1", "type": "hypothesis", "text": "Likely cause", "score": 1}],
                    "edges": [],
                }),
                encoding="utf-8",
            )

            patch_path.write_text(json.dumps({"update_nodes": [{"id": "A2", "set": {"score": 3}}]}), encoding="utf-8")
            missing = self.run_cli("record", str(state_path), "--patch", str(patch_path))
            self.assertNotEqual(missing.returncode, 0, missing.stdout)
            self.assertIn("update_nodes id A2 does not exist", missing.stderr)

            patch_path.write_text(json.dumps({"update_nodes": [{"id": "A1", "set": {"type": "hypothesis"}}]}), encoding="utf-8")
            identity = self.run_cli("record", str(state_path), "--patch", str(patch_path))
            self.assertNotEqual(identity.returncode, 0, identity.stdout)
            self.assertIn("update_nodes[0].set cannot change type", identity.stderr)

    def test_init_emits_valid_starter_states(self) -> None:
        init = self.run_cli("init", "--goal", "Diagnose production outage")
        self.assertEqual(init.returncode, 0, init.stderr)
        init_state = json.loads(init.stdout)
        self.assertEqual(init_state["nodes"][0]["id"], "G1")
        self.assertEqual(init_state["nodes"][0]["text"], "Diagnose production outage")

        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "starter.json"
            state_path.write_text(init.stdout, encoding="utf-8")
            valid = self.run_cli("audit", str(state_path))
            self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_init_names_the_goal_it_created(self) -> None:
        # All 12 duplicate-id failures of the #37 loop were a first patch adding G1 again:
        # init created it and said nothing (issue #38).
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"

            init = self.run_cli("init", "--goal", " Diagnose outage ", "-o", str(state_path))

            self.assertEqual(init.returncode, 0, init.stderr)
            self.assertEqual(init.stdout, f"created {state_path} with goal G1: Diagnose outage\n")

        to_stdout = self.run_cli("init", "--goal", "Diagnose outage")
        self.assertEqual(json.loads(to_stdout.stdout)["nodes"], [{"id": "G1", "type": "goal", "text": "Diagnose outage"}])
        self.assertEqual(to_stdout.stderr, "")

    def test_record_enables_fresh_init_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            patch_path = Path(tmp_dir) / "patch.json"
            init = self.run_cli("init", "--goal", "Diagnose outage", "-o", str(state_path))
            self.assertEqual(init.returncode, 0, init.stderr)

            patch = {
                "nodes": [
                    {"id": "E1", "type": "observation", "text": "API error rate increased", "score": 5},
                    {"id": "A1", "type": "hypothesis", "text": "Database latency is causing errors", "score": 2},
                    {"id": "T1", "type": "test", "text": "Check database latency metrics"},
                ],
                "edges": [
                    {"from": "E1", "to": "A1", "type": "supports", "score": 3},
                    {"from": "A1", "to": "T1", "type": "prompts"},
                ],
            }
            patch_path.write_text(json.dumps(patch), encoding="utf-8")
            recorded = self.run_cli("record", str(state_path), "--patch", str(patch_path))
            self.assertEqual(recorded.returncode, 0, recorded.stderr)
            recorded_state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual([node["id"] for node in recorded_state["nodes"]], ["G1", "E1", "A1", "T1"])
            self.assertTrue(state_path.with_suffix(".html").is_file())

            valid = self.run_cli("audit", str(state_path))
            self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_audit_fixture_passes(self) -> None:
        audit = self.run_cli("audit", str(FIXTURE))
        self.assertEqual(audit.returncode, 0, audit.stderr)
        self.assertEqual(audit.stdout, "answer CS1 (Candidate from A1) wins.: checks pass\n")

    def test_audit_accepts_evidence_and_rejects_legacy_fact_contradiction_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "evidence-state.json"
            legacy_path = Path(tmp_dir) / "legacy-state.json"
            evidence_state = {
                "nodes": [
                    {"id": "G1", "type": "goal", "text": "Pick cause"},
                    {"id": "A1", "type": "hypothesis", "text": "Likely cause", "score": 3},
                    {"id": "E1", "type": "observation", "text": "Observed mismatch", "score": 5},
                    {"id": "CS1", "type": "candidate_solution", "text": "Candidate", "answer_kind": "exact_answer"},
                ],
                "edges": [
                    {"from": "E1", "to": "A1", "type": "contradicts"},
                    {"from": "A1", "to": "CS1", "type": "leads_to"},
                    {"from": "CS1", "to": "G1", "type": "answers"},
                ],
            }
            legacy_state = {
                "nodes": [
                    {"id": "G1", "type": "goal", "text": "Pick cause"},
                    {"id": "F1", "type": "fact", "text": "Legacy fact"},
                    {"id": "X1", "type": "contradiction", "text": "Legacy contradiction"},
                ],
                "edges": [],
            }
            state_path.write_text(json.dumps(evidence_state), encoding="utf-8")
            legacy_path.write_text(json.dumps(legacy_state), encoding="utf-8")

            valid = self.run_cli("audit", str(state_path))
            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertEqual(valid.stdout.splitlines()[0], "no answer claimed")

            invalid = self.run_cli("audit", str(legacy_path))
            self.assertNotEqual(invalid.returncode, 0, invalid.stdout)
            self.assertIn("invalid type 'fact'", invalid.stderr)
            self.assertIn("invalid type 'contradiction'", invalid.stderr)

    def test_audit_requires_answers_edge_for_candidate_goal_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            invalid_path = Path(tmp_dir) / "invalid-candidate-goal-link.json"
            invalid_state = {
                "nodes": [
                    {"id": "G1", "type": "goal", "text": "Pick cause"},
                    {"id": "A1", "type": "hypothesis", "text": "Likely cause", "score": 3},
                    {"id": "CS1", "type": "candidate_solution", "text": "Candidate", "answer_kind": "exact_answer"},
                ],
                "edges": [
                    {"from": "A1", "to": "CS1", "type": "leads_to"},
                    {"from": "CS1", "to": "G1", "type": "leads_to"},
                    {"from": "A1", "to": "G1", "type": "answers"},
                ],
            }
            invalid_path.write_text(json.dumps(invalid_state), encoding="utf-8")

            invalid = self.run_cli("audit", str(invalid_path))
            self.assertNotEqual(invalid.returncode, 0, invalid.stdout)
            self.assertIn("candidate_solution -> goal must use answers", invalid.stderr)
            self.assertIn("answers edge must connect candidate_solution -> goal", invalid.stderr)

    def test_audit_accepts_prompts_edge_for_follow_up_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "prompts-edge-state.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "hypothesis", "text": "Likely cause", "score": 3},
                    {"id": "T1", "type": "test", "text": "Check likely cause"},
                ],
                "edges": [{"from": "A1", "to": "T1", "type": "prompts"}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            valid = self.run_cli("audit", str(state_path))
            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertEqual(valid.stdout.splitlines()[0], "no answer claimed")

    def test_beliefs_use_evidence_scores(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "evidence-state.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "hypothesis", "text": "Likely cause"},
                    {"id": "E1", "type": "observation", "text": "Positive signal"},
                    {"id": "E2", "type": "observation", "text": "Negative signal"},
                ],
                "edges": [
                    {"from": "E1", "to": "A1", "type": "supports", "score": 4},
                    {"from": "E2", "to": "A1", "type": "contradicts"},
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            self.assertEqual(self.run_cli("audit", str(state_path)).returncode, 0)
            # Default odds 1 * ratio 3 * default ratio 1/2 = odds 1.5 => belief 0.6 => -ln(.6).
            self.assertAlmostEqual(truth_cost(state, "A1"), 0.510826, places=6)

    def test_beliefs_propagate_leads_to_premises(self) -> None:
        state = {
            "nodes": [
                {"id": "A1", "type": "hypothesis", "text": "Premise A", "score": 4},
                {"id": "E1", "type": "observation", "text": "Premise E"},
                {"id": "D1", "type": "hypothesis", "text": "Derived from A and E"},
            ],
            "edges": [
                {"from": "A1", "to": "D1", "type": "leads_to"},
                {"from": "E1", "to": "D1", "type": "leads_to"},
            ],
        }

        self.assertAlmostEqual(truth_cost(state, "A1"), 0.356675, places=6)
        # D1 truth is graph-derived from both premises: -ln(0.7 * 0.9).
        self.assertAlmostEqual(truth_cost(state, "D1"), 0.462035, places=6)

    def test_beliefs_factor_replaces_correlated_likelihood_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "factor-likelihood-state.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "hypothesis", "text": "Likely cause", "score": 3},
                    {"score": 5, "id": "E1", "type": "observation", "text": "Positive signal A"},
                    {"score": 5, "id": "E2", "type": "observation", "text": "Positive signal B"},
                    {"score": 5, "id": "E3", "type": "observation", "text": "Independent signal"},
                ],
                "edges": [
                    {"from": "E1", "to": "A1", "type": "supports"},
                    {"from": "E2", "to": "A1", "type": "supports"},
                    {"from": "E3", "to": "A1", "type": "supports"},
                ],
                "factors": [{"id": "F1", "edges": ["E1-A1", "E2-A1"], "score": 4, "note": "E1 and E2 are correlated, so they count once."}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            # Default odds 1 * group ratio 3 * independent default ratio 2 = odds 6 => belief 6/7 => -ln(6/7).
            self.assertAlmostEqual(truth_cost(state, "A1"), 0.154151, places=6)

            valid = self.run_cli("audit", str(state_path))
            self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_beliefs_leads_to_factor_replaces_independent_member_costs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "factor-leads-to-state.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "hypothesis", "text": "Premise A", "score": 1},
                    {"id": "B1", "type": "observation", "text": "Premise B", "score": 2},
                    {"id": "C1", "type": "hypothesis", "text": "Independent premise C"},
                    {"id": "D1", "type": "hypothesis", "text": "Derived from A, B, and C"},
                ],
                "edges": [
                    {"from": "A1", "to": "D1", "type": "leads_to"},
                    {"from": "B1", "to": "D1", "type": "leads_to"},
                    {"from": "C1", "to": "D1", "type": "leads_to"},
                ],
                "factors": [{"id": "F1", "edges": ["A1-D1", "B1-D1"], "score": 2, "note": "A1 and B1 share a latent source."}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            # Joint 0.3 replaces 0.1 * 0.3; the independent premise adds its default 0.5: -ln(0.15).
            self.assertAlmostEqual(truth_cost(state, "D1"), 1.897120, places=6)

            valid = self.run_cli("audit", str(state_path))
            self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_audit_rejects_raw_leads_to_cycle_even_when_grouped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "grouped-cycle-state.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "hypothesis", "text": "Premise A", "score": 3},
                    {"id": "B1", "type": "hypothesis", "text": "Premise B", "score": 3},
                    {"id": "D1", "type": "hypothesis", "text": "Derived claim"},
                ],
                "edges": [
                    {"from": "A1", "to": "D1", "type": "leads_to"},
                    {"from": "B1", "to": "D1", "type": "leads_to"},
                    {"from": "D1", "to": "A1", "type": "leads_to"},
                ],
                "factors": [{"id": "F1", "edges": ["A1-D1", "B1-D1"], "score": 2, "note": "A group must not hide the raw cycle."}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            invalid = self.run_cli("audit", str(state_path))
            self.assertNotEqual(invalid.returncode, 0, invalid.stdout)
            self.assertIn("cycle in truth dependency graph", invalid.stderr)

    def test_record_patch_upserts_new_factors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "record-factor-state.json"
            patch_path = Path(tmp_dir) / "record-factor-patch.json"
            output_path = Path(tmp_dir) / "record-factor-output.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "hypothesis", "text": "Likely cause", "score": 3},
                    {"score": 5, "id": "E1", "type": "observation", "text": "Positive signal A"},
                    {"score": 5, "id": "E2", "type": "observation", "text": "Positive signal B"},
                ],
                "edges": [{"from": "E1", "to": "A1", "type": "supports"}],
            }
            patch = {
                "edges": [{"from": "E2", "to": "A1", "type": "supports"}],
                "factors": [{"id": "F1", "edges": ["E1-A1", "E2-A1"], "score": 4, "note": "E1 and E2 share source."}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            patch_path.write_text(json.dumps(patch), encoding="utf-8")

            result = self.run_cli("record", str(state_path), "--patch", str(patch_path), "-o", str(output_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            recorded = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(recorded["factors"][0]["id"], "F1")
            # Group score 4 is ratio 3, replacing the two member ratios of 2 => odds 3 => -ln(0.75).
            self.assertAlmostEqual(truth_cost(recorded, "A1"), 0.287682, places=6)

    def test_legacy_edge_strength_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "legacy-contradiction-state.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "hypothesis", "text": "Likely cause"},
                    {"id": "E1", "type": "observation", "text": "Negative signal"},
                ],
                "edges": [{"from": "E1", "to": "A1", "type": "contradicts", "strength": 1.0}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            valid = self.run_cli("audit", str(state_path))
            self.assertNotEqual(valid.returncode, 0, valid.stdout)
            self.assertIn("ignored legacy field(s) strength", valid.stderr)
            self.assertIn("schema $.edges[0]", valid.stderr)

    def test_mermaid_and_html_smoke(self) -> None:
        mermaid = self.run_cli("mermaid", str(FIXTURE))
        self.assertEqual(mermaid.returncode, 0, mermaid.stderr)
        self.assertIn("flowchart", mermaid.stdout)

        with tempfile.TemporaryDirectory() as tmp_dir:
            html_path = Path(tmp_dir) / "graph.html"
            html = self.run_cli("html", str(FIXTURE), "-o", str(html_path))
            self.assertEqual(html.returncode, 0, html.stderr)
            html_text = html_path.read_text(encoding="utf-8")
            self.assertIn("<!doctype html>", html_text.lower())
            self.assertIn("Full audit graph", html_text)
            self.assertIn("https://cdn.jsdelivr.net", html_text)
            self.assertIn("type=\"module\"", html_text)
            self.assertIn("class=\"mermaid\"", html_text)

            offline_path = Path(tmp_dir) / "graph-offline.html"
            offline = self.run_cli("html", str(FIXTURE), "--offline", "-o", str(offline_path))
            self.assertEqual(offline.returncode, 0, offline.stderr)
            offline_text = offline_path.read_text(encoding="utf-8")
            self.assertIn("<svg", offline_text)
            self.assertIn("Mermaid source", offline_text)
            self.assertNotIn("https://cdn.jsdelivr.net", offline_text)
            self.assertNotIn("type=\"module\"", offline_text)

    def test_offline_html_uses_collision_safe_render_identities(self) -> None:
        state = {
            "nodes": [
                {"id": "A.B", "type": "candidate_solution", "text": "hyphen", "answer_kind": "exact_answer", "score": 3},
                {"id": "A_B", "type": "candidate_solution", "text": "underscore", "answer_kind": "exact_answer", "score": 2},
                {"id": "A B", "type": "goal", "text": "space"},
            ],
            "edges": [
                {"from": "A.B", "to": "A B", "type": "answers"},
                {"from": "A_B", "to": "A B", "type": "answers"},
            ],
            "report": {"candidates": [{"id": "A.B"}, {"id": "A_B"}]},
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            html_path = Path(tmp_dir) / "graph.html"
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = self.run_cli("html", str(state_path), "--offline", "-o", str(html_path))

            self.assertEqual(result.returncode, 0, result.stderr)
            output = html_path.read_text(encoding="utf-8")
            for raw_id, render_id in (("A B", "A_B"), ("A.B", "A_B_2"), ("A_B", "A_B_3")):
                self.assertIn(f'id="{render_id}" class="node" data-node-id="{raw_id}"', output)
                self.assertIn(f'href="#details-{render_id}"', output)
                self.assertIn(f'id="details-{render_id}"', output)
            self.assertIn('"from": "A_B_2", "to": "A_B"', output)
            self.assertIn('"from": "A_B_3", "to": "A_B"', output)
            self.assertIn('<option value="A_B_2">A.B</option>', output)
            self.assertIn('<option value="A_B_3">A_B</option>', output)
            self.assertIn('"A_B_2": ["A_B_2"]', output)
            self.assertIn('"A_B_3": ["A_B_3"]', output)

    def test_mermaid_and_html_render_virtual_factors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "factor-render-state.json"
            html_path = Path(tmp_dir) / "factor-render.html"
            state = {
                "nodes": [
                    {"id": "A1", "type": "hypothesis", "text": "Likely cause", "score": 3},
                    {"score": 5, "id": "E1", "type": "observation", "text": "Positive signal A"},
                    {"score": 5, "id": "E2", "type": "observation", "text": "Positive signal B"},
                ],
                "edges": [
                    {"from": "E1", "to": "A1", "type": "supports"},
                    {"from": "E2", "to": "A1", "type": "supports"},
                ],
                "factors": [{"id": "F1", "edges": ["E1-A1", "E2-A1"], "score": 4, "note": "E1 and E2 share source."}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            mermaid = self.run_cli("mermaid", str(state_path))
            self.assertEqual(mermaid.returncode, 0, mermaid.stderr)
            self.assertIn("F1", mermaid.stdout)
            self.assertIn("grouped supports", mermaid.stdout)
            self.assertIn("supports factor", mermaid.stdout)
            self.assertIn("supports group, score 4", mermaid.stdout)

            html = self.run_cli("html", str(state_path), "--offline", "-o", str(html_path))
            self.assertEqual(html.returncode, 0, html.stderr)
            html_text = html_path.read_text(encoding="utf-8")
            self.assertIn('data-factor-id="F1"', html_text)
            self.assertIn('class="node factor"', html_text)
            self.assertIn("grouped supports", html_text)
            self.assertIn("supports factor", html_text)
            self.assertNotIn('LS-E1 LE-A1', html_text)
            self.assertNotIn("https://cdn.jsdelivr.net", html_text)


if __name__ == "__main__":
    unittest.main()
