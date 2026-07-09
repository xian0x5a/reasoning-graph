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


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
PACKAGE_SRC_ROOT = PACKAGE_ROOT / "src"
sys.path.insert(0, str(PACKAGE_SRC_ROOT))

from reasoning_graph.frontier import search_cursor


FIXTURE = PACKAGE_ROOT / "tests" / "fixtures" / "valid" / "reasoning-graph-strict-good.json"
STATE_SCHEMA = PACKAGE_SRC_ROOT / "reasoning_graph" / "schemas" / "state.schema.json"
PATCH_SCHEMA = PACKAGE_SRC_ROOT / "reasoning_graph" / "schemas" / "patch.schema.json"


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

    def test_json_schemas_parse_and_cover_core_enums(self) -> None:
        state_schema = json.loads(STATE_SCHEMA.read_text(encoding="utf-8"))
        patch_schema = json.loads(PATCH_SCHEMA.read_text(encoding="utf-8"))

        self.assertEqual(state_schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertIn("candidate_solution", state_schema["$defs"]["node"]["properties"]["type"]["enum"])
        self.assertIn("answers", state_schema["$defs"]["edge"]["properties"]["type"]["enum"])
        self.assertIn("frontier_exhausted", state_schema["$defs"]["event"]["properties"]["outcome"]["enum"])
        self.assertIn("seed", state_schema["$defs"]["event"]["properties"]["action"]["enum"])
        self.assertIn("assign", state_schema["$defs"]["event"]["properties"]["action"]["enum"])
        self.assertIn("exact_answer", state_schema["$defs"]["node"]["properties"]["answer_kind"]["enum"])
        self.assertIn("stop_outcome", patch_schema["properties"])
        serialized_schemas = json.dumps({"state": state_schema, "patch": patch_schema})
        self.assertNotIn('"deprecated"', serialized_schemas)
        self.assertNotIn('"solutions"', state_schema["properties"])
        self.assertNotIn('"label"', state_schema["$defs"]["edge"]["properties"])
        self.assertNotIn('"path_cost"', state_schema["$defs"]["frontierItem"]["properties"])
        self.assertNotIn("solution", state_schema["$defs"]["event"]["properties"]["action"]["enum"])
        self.assertNotIn('"solution_node"', patch_schema["properties"])
        self.assertNotIn('"no_reopen_reason"', patch_schema["properties"])

    def test_schema_command_emits_packaged_schema_json(self) -> None:
        result = self.run_cli("schema", "state")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), json.loads(STATE_SCHEMA.read_text(encoding="utf-8")))

    def test_schema_command_writes_patch_schema_to_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "patch.schema.json"

            result = self.run_cli("schema", "patch", "-o", str(output_path))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(json.loads(output_path.read_text(encoding="utf-8")), json.loads(PATCH_SCHEMA.read_text(encoding="utf-8")))

    def test_mutating_commands_rewrite_state_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            state_path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

            result = self.run_cli("costs", str(state_path))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertTrue(all("search_cost" in item for item in state["frontier"]))

    def test_output_path_overrides_default_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            output_path = Path(tmp_dir) / "costs.json"
            original = FIXTURE.read_text(encoding="utf-8")
            state_path.write_text(original, encoding="utf-8")

            result = self.run_cli("costs", str(state_path), "-o", str(output_path))

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original)
            self.assertTrue(output_path.is_file())

    def test_output_dash_emits_stdout_without_mutating_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            original = FIXTURE.read_text(encoding="utf-8")
            state_path.write_text(original, encoding="utf-8")

            result = self.run_cli("costs", str(state_path), "-o", "-")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original)
            state = json.loads(result.stdout)
            self.assertTrue(all("search_cost" in item for item in state["frontier"]))

    def test_next_pop_rewrites_state_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            state_path.write_text(
                json.dumps({
                    "nodes": [{"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 0.2}],
                    "edges": [],
                    "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
                }),
                encoding="utf-8",
            )

            result = self.run_cli("next", str(state_path), "--pop")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("next Q1", result.stdout)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual([event["action"] for event in state["events"]], ["init", "pop"])

    def test_next_pop_output_dash_emits_mutated_state_without_mutating_input(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            original_state = {
                "nodes": [{"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 0.2}],
                "edges": [],
                "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
            }
            original = json.dumps(original_state)
            state_path.write_text(original, encoding="utf-8")

            result = self.run_cli("next", str(state_path), "--pop", "-o", "-")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original)
            persisted = json.loads(result.stdout)
            self.assertEqual([event["action"] for event in persisted["events"]], ["init", "pop"])

    def test_next_pop_stdin_emits_mutated_state_to_stdout(self) -> None:
        state = json.dumps({
            "nodes": [{"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 0.2}],
            "edges": [],
            "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
        })

        result = self.run_cli("next", "-", "--pop", input=state)

        self.assertEqual(result.returncode, 0, result.stderr)
        persisted = json.loads(result.stdout)
        self.assertEqual([event["action"] for event in persisted["events"]], ["init", "pop"])

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
            "nodes": [{"id": "A3", "type": "assumption", "text": "Third cause", "prior": 0.2}],
            "update_nodes": [{"id": "A1", "set": {"posterior": 0.7}}],
            "edges": [{"id": "E3", "from": "A3", "to": "CS1", "type": "supports"}],
            "frontier": [{"id": "Q4", "node": "A3", "cost_components": {"truth": "auto"}}],
            "stop_reason": "sample stop",
            "stop_outcome": "user_stopped",
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
            patch_validator.validate({"stop_reason": "missing outcome"})

        with self.assertRaises(jsonschema.ValidationError):
            patch_validator.validate({"update_nodes": [{"id": "A1", "set": {"id": "A2"}}]})

    def test_expand_patch_updates_existing_node_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            patch_path = Path(tmp_dir) / "patch.json"
            state_path.write_text(
                json.dumps({
                    "nodes": [{"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 0.2}],
                    "edges": [],
                    "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
                }),
                encoding="utf-8",
            )
            popped = self.run_cli("next", str(state_path), "--pop", "-i")
            self.assertEqual(popped.returncode, 0, popped.stderr)

            patch_path.write_text(
                json.dumps({
                    "update_nodes": [{"id": "A1", "set": {"posterior": 0.75, "exhausted": True, "exhaustion_reason": "cheap checks complete"}}],
                    "no_new_work_reason": "Only A1 score/exhaustion changed; no child work remains.",
                }),
                encoding="utf-8",
            )

            expanded = self.run_cli("expand", str(state_path), "--item", "Q1", "--patch", str(patch_path), "-i")
            self.assertEqual(expanded.returncode, 0, expanded.stderr)
            updated = json.loads(state_path.read_text(encoding="utf-8"))

            self.assertEqual(updated["nodes"][0]["posterior"], 0.75)
            self.assertTrue(updated["nodes"][0]["exhausted"])
            self.assertEqual(updated["nodes"][0]["exhaustion_reason"], "cheap checks complete")
            self.assertEqual(
                updated["events"][-1]["updated_nodes"],
                [{"id": "A1", "fields": ["exhausted", "exhaustion_reason", "posterior"]}],
            )
            self.assertEqual(updated["events"][-1]["updated_node_snapshots"][0]["before"]["prior"], 0.2)

    def test_expand_patch_rejects_missing_or_identity_node_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            patch_path = Path(tmp_dir) / "patch.json"
            state_path.write_text(
                json.dumps({
                    "nodes": [{"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 0.2}],
                    "edges": [],
                    "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
                }),
                encoding="utf-8",
            )
            popped = self.run_cli("next", str(state_path), "--pop", "-i")
            self.assertEqual(popped.returncode, 0, popped.stderr)

            patch_path.write_text(json.dumps({"update_nodes": [{"id": "A2", "set": {"posterior": 0.5}}]}), encoding="utf-8")
            missing = self.run_cli("expand", str(state_path), "--item", "Q1", "--patch", str(patch_path), "-i")
            self.assertNotEqual(missing.returncode, 0, missing.stdout)
            self.assertIn("update_nodes id A2 does not exist", missing.stderr)

            patch_path.write_text(json.dumps({"update_nodes": [{"id": "A1", "set": {"type": "derived"}}]}), encoding="utf-8")
            identity = self.run_cli("expand", str(state_path), "--item", "Q1", "--patch", str(patch_path), "-i")
            self.assertNotEqual(identity.returncode, 0, identity.stdout)
            self.assertIn("update_nodes[0].set cannot change type", identity.stderr)

    def test_costs_reject_legacy_path_cost_at_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "legacy-path-cost.json"
            state_path.write_text(
                json.dumps({
                    "nodes": [{"id": "G1", "type": "goal", "text": "Solve"}],
                    "edges": [],
                    "frontier": [{"id": "Q1", "node": "G1", "path_cost": 1.0}],
                }),
                encoding="utf-8",
            )

            result = self.run_cli("costs", str(state_path))
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("rejected legacy field path_cost", result.stderr)

    def test_init_emits_valid_starter_states(self) -> None:
        benchmark = self.run_cli("init", "--goal", "Benchmark solve", "--profile", "benchmark")
        self.assertEqual(benchmark.returncode, 0, benchmark.stderr)
        benchmark_state = json.loads(benchmark.stdout)
        self.assertEqual(benchmark_state["nodes"][0]["id"], "G1")
        self.assertEqual(benchmark_state["nodes"][0]["text"], "Benchmark solve")
        self.assertEqual(benchmark_state["stop_policy"]["severity"], "error")
        self.assertEqual(benchmark_state["branch_policy"]["enforce_on"], "always")

        init = self.run_cli("init", "--goal", "Diagnose production outage", "--strict")
        self.assertEqual(init.returncode, 0, init.stderr)
        init_state = json.loads(init.stdout)
        self.assertEqual(init_state["nodes"][0]["text"], "Diagnose production outage")
        self.assertEqual(init_state["stop_policy"]["severity"], "error")

        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "starter.json"
            state_path.write_text(benchmark.stdout, encoding="utf-8")
            valid = self.run_cli("validate", str(state_path))
            self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_seed_enables_fresh_init_next_pop_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            seed_path = Path(tmp_dir) / "seed.json"
            init = self.run_cli("init", "--goal", "Diagnose outage", "--strict", "-o", str(state_path))
            self.assertEqual(init.returncode, 0, init.stderr)

            empty_next = self.run_cli("next", str(state_path), "--pop", "-i")
            self.assertNotEqual(empty_next.returncode, 0, empty_next.stdout)
            self.assertIn("active frontier is empty", empty_next.stderr)

            seed_path.write_text(
                json.dumps({
                    "nodes": [
                        {"id": "E1", "type": "evidence", "text": "API error rate increased", "confidence": 0.9},
                        {"id": "A1", "type": "assumption", "text": "Database latency is causing errors", "prior": 0.4},
                        {"id": "T1", "type": "test", "text": "Check database latency metrics"},
                    ],
                    "edges": [
                        {"id": "E1-A1", "from": "E1", "to": "A1", "type": "supports", "likelihood_ratio": 2.0},
                        {"id": "A1-T1", "from": "A1", "to": "T1", "type": "prompts"},
                    ],
                    "frontier": [
                        {
                            "id": "Q1",
                            "node": "T1",
                            "related": ["E1", "A1"],
                            "cost_components": {"truth": "auto", "verification": 0.1, "effort_budget": 0.2},
                            "budget": {"max_seconds": 300, "stop_after": "first discriminating metric"},
                        }
                    ],
                }),
                encoding="utf-8",
            )

            seeded = self.run_cli("seed", str(state_path), "--patch", str(seed_path), "-i")
            self.assertEqual(seeded.returncode, 0, seeded.stderr)
            seeded_state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertNotIn("events", seeded_state)
            self.assertNotIn("parent", seeded_state["frontier"][0])
            self.assertIn("search_cost", seeded_state["frontier"][0])

            valid = self.run_cli("validate", str(state_path))
            self.assertEqual(valid.returncode, 0, valid.stderr)

            popped = self.run_cli("next", str(state_path), "--pop", "-i")
            self.assertEqual(popped.returncode, 0, popped.stderr)
            self.assertIn("next Q1", popped.stdout)
            popped_state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual([event["action"] for event in popped_state["events"]], ["init", "pop"])
            self.assertEqual(popped_state["events"][0]["frontier"], ["Q1"])

            second_state_path = Path(tmp_dir) / "second-state.json"
            second_init = self.run_cli("init", "--goal", "Solve the problem", "--strict", "-o", str(second_state_path))
            self.assertEqual(second_init.returncode, 0, second_init.stderr)
            second_seeded = self.run_cli("seed", str(second_state_path), "--patch", str(seed_path), "-i")
            self.assertEqual(second_seeded.returncode, 0, second_seeded.stderr)
            second_popped = self.run_cli("next", str(second_state_path), "--pop", "-i")
            self.assertEqual(second_popped.returncode, 0, second_popped.stderr)
            self.assertIn("next Q1", second_popped.stdout)

    def test_seed_rejects_non_root_frontier_and_can_add_later_root_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            bad_seed_path = Path(tmp_dir) / "bad-seed.json"
            good_seed_path = Path(tmp_dir) / "good-seed.json"
            init = self.run_cli("init", "--goal", "Diagnose outage", "-o", str(state_path))
            self.assertEqual(init.returncode, 0, init.stderr)

            bad_seed_path.write_text(
                json.dumps({
                    "nodes": [{"id": "T1", "type": "test", "text": "Check logs"}],
                    "frontier": [{"id": "Q1", "node": "T1", "parent": "Q0"}],
                }),
                encoding="utf-8",
            )
            bad = self.run_cli("seed", str(state_path), "--patch", str(bad_seed_path), "-i")
            self.assertNotEqual(bad.returncode, 0, bad.stdout)
            self.assertIn("must be a root item without parent", bad.stderr)

            good_seed_path.write_text(
                json.dumps({
                    "nodes": [{"id": "T1", "type": "test", "text": "Check logs"}],
                    "frontier": [{"id": "Q1", "node": "T1", "cost_components": {"truth": "auto"}}],
                }),
                encoding="utf-8",
            )
            good = self.run_cli("seed", str(state_path), "--patch", str(good_seed_path), "-i")
            self.assertEqual(good.returncode, 0, good.stderr)
            popped = self.run_cli("next", str(state_path), "--pop", "-i")
            self.assertEqual(popped.returncode, 0, popped.stderr)
            later_without_reason_path = Path(tmp_dir) / "later-without-reason.json"
            later_with_reason_path = Path(tmp_dir) / "later-with-reason.json"
            later_without_reason_path.write_text(
                json.dumps({
                    "nodes": [{"id": "T2", "type": "test", "text": "Check deploy log"}],
                    "frontier": [{"id": "Q2", "node": "T2", "cost_components": {"truth": "auto"}}],
                }),
                encoding="utf-8",
            )
            missing_reason = self.run_cli("seed", str(state_path), "--patch", str(later_without_reason_path), "-i")
            self.assertNotEqual(missing_reason.returncode, 0, missing_reason.stdout)
            self.assertIn("requires patch.reason", missing_reason.stderr)

            later_with_reason_path.write_text(
                json.dumps({
                    "reason": "New root hypothesis from user inspiration",
                    "nodes": [{"id": "T2", "type": "test", "text": "Check deploy log"}],
                    "frontier": [{"id": "Q2", "node": "T2", "cost_components": {"truth": "auto"}}],
                }),
                encoding="utf-8",
            )
            later_seed = self.run_cli("seed", str(state_path), "--patch", str(later_with_reason_path), "-i")
            self.assertEqual(later_seed.returncode, 0, later_seed.stderr)
            seeded_later_state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual([event["action"] for event in seeded_later_state["events"]], ["init", "pop", "seed"])
            self.assertEqual(seeded_later_state["events"][-1]["add_frontier"], ["Q2"])
            self.assertNotIn("parent", next(item for item in seeded_later_state["frontier"] if item["id"] == "Q2"))

            expansion_path = Path(tmp_dir) / "expansion.json"
            expansion_path.write_text(json.dumps({"no_new_work_reason": "first root item closed"}), encoding="utf-8")
            expanded = self.run_cli("expand", str(state_path), "--item", "Q1", "--patch", str(expansion_path), "-i")
            self.assertEqual(expanded.returncode, 0, expanded.stderr)
            later_pop = self.run_cli("next", str(state_path), "--pop", "-i")
            self.assertEqual(later_pop.returncode, 0, later_pop.stderr)
            self.assertIn("next Q2", later_pop.stdout)

    def test_stop_review_passes_fixture_and_fails_missing_viable_candidate(self) -> None:
        ok = self.run_cli("stop-review", str(FIXTURE))
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("verdict: pass", ok.stdout)
        self.assertIn("best candidate answers an accepted goal", ok.stdout)

        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "missing-candidate.json"
            state = json.loads(FIXTURE.read_text(encoding="utf-8"))
            state["edges"] = [edge for edge in state["edges"] if edge.get("type") != "answers"]
            state_path.write_text(json.dumps(state), encoding="utf-8")

            missing = self.run_cli("stop-review", str(state_path))
            self.assertNotEqual(missing.returncode, 0, missing.stdout)
            self.assertIn("verdict: fail", missing.stdout)
            self.assertIn("requires a viable candidate_solution", missing.stdout)

    def test_stop_review_compares_optional_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            draft_path = Path(tmp_dir) / "answer.md"
            draft_path.write_text("Candidate from A1 is the answer.", encoding="utf-8")
            ok = self.run_cli("stop-review", str(FIXTURE), "--draft", str(draft_path), "--strict-warnings")
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertIn("verdict: pass", ok.stdout)

            draft_path.write_text("Unrelated answer.", encoding="utf-8")
            missing = self.run_cli("stop-review", str(FIXTURE), "--draft", str(draft_path), "--strict-warnings")
            self.assertNotEqual(missing.returncode, 0, missing.stdout)
            self.assertIn("draft does not mention best candidate", missing.stdout)

    def test_doctor_reports_validation_and_audit_health(self) -> None:
        ok = self.run_cli("doctor", str(FIXTURE))
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("doctor: validation ok", ok.stdout)
        self.assertIn("doctor: audit ok", ok.stdout)

        with tempfile.TemporaryDirectory() as tmp_dir:
            invalid_path = Path(tmp_dir) / "invalid.json"
            invalid_path.write_text(json.dumps({"nodes": [{"id": "X1", "type": "fact"}]}), encoding="utf-8")
            invalid = self.run_cli("doctor", str(invalid_path))
            self.assertNotEqual(invalid.returncode, 0, invalid.stdout)
            self.assertIn("invalid type 'fact'", invalid.stderr)
            self.assertIn("doctor: validation failed", invalid.stdout)

    def test_validate_and_audit_fixture_pass(self) -> None:
        validate = self.run_cli("validate", str(FIXTURE))
        self.assertEqual(validate.returncode, 0, validate.stderr)
        self.assertIn("ok", validate.stdout)

        audit = self.run_cli("audit", str(FIXTURE))
        self.assertEqual(audit.returncode, 0, audit.stderr)
        self.assertIn("ok", audit.stdout)

    def test_audit_reports_validation_errors_without_deeper_audit_crash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "invalid-stop-policy.json"
            state = {
                "nodes": [],
                "edges": [],
                "frontier": [],
                "stop_policy": {"max_live_frontier_items": "x", "min_viable_candidates": "y"},
                "events": [
                    {"step": 1, "action": "init", "frontier": []},
                    {"step": 2, "action": "stop", "reason": "manual stop", "outcome": "user_stopped"},
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            audit = self.run_cli("audit", str(state_path))

            self.assertNotEqual(audit.returncode, 0, audit.stdout)
            self.assertIn("stop_policy.max_live_frontier_items must be a non-negative integer", audit.stderr)
            self.assertIn("stop_policy.min_viable_candidates must be a non-negative integer", audit.stderr)
            self.assertNotIn("invalid literal for int()", audit.stderr)

    def test_validate_accepts_evidence_and_rejects_legacy_fact_contradiction_nodes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "evidence-state.json"
            legacy_path = Path(tmp_dir) / "legacy-state.json"
            evidence_state = {
                "nodes": [
                    {"id": "G1", "type": "goal", "text": "Pick cause"},
                    {"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 0.6},
                    {"id": "E1", "type": "evidence", "text": "Observed mismatch", "confidence": 0.9},
                    {"id": "CS1", "type": "candidate_solution", "text": "Candidate", "answer_kind": "exact_answer"},
                ],
                "edges": [
                    {"from": "E1", "to": "A1", "type": "contradicts"},
                    {"from": "A1", "to": "CS1", "type": "leads_to"},
                    {"from": "CS1", "to": "G1", "type": "answers"},
                ],
                "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
            }
            legacy_state = {
                "nodes": [
                    {"id": "G1", "type": "goal", "text": "Pick cause"},
                    {"id": "F1", "type": "fact", "text": "Legacy fact"},
                    {"id": "X1", "type": "contradiction", "text": "Legacy contradiction"},
                ],
                "edges": [],
                "frontier": [],
            }
            state_path.write_text(json.dumps(evidence_state), encoding="utf-8")
            legacy_path.write_text(json.dumps(legacy_state), encoding="utf-8")

            valid = self.run_cli("validate", str(state_path))
            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertIn("ok", valid.stdout)

            invalid = self.run_cli("validate", str(legacy_path))
            self.assertNotEqual(invalid.returncode, 0, invalid.stdout)
            self.assertIn("invalid type 'fact'", invalid.stderr)
            self.assertIn("invalid type 'contradiction'", invalid.stderr)

    def test_validate_requires_answers_edge_for_candidate_goal_link(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            invalid_path = Path(tmp_dir) / "invalid-candidate-goal-link.json"
            invalid_state = {
                "nodes": [
                    {"id": "G1", "type": "goal", "text": "Pick cause"},
                    {"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 0.6},
                    {"id": "CS1", "type": "candidate_solution", "text": "Candidate", "answer_kind": "exact_answer"},
                ],
                "edges": [
                    {"from": "A1", "to": "CS1", "type": "leads_to"},
                    {"from": "CS1", "to": "G1", "type": "leads_to"},
                    {"from": "A1", "to": "G1", "type": "answers"},
                ],
                "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
            }
            invalid_path.write_text(json.dumps(invalid_state), encoding="utf-8")

            invalid = self.run_cli("validate", str(invalid_path))
            self.assertNotEqual(invalid.returncode, 0, invalid.stdout)
            self.assertIn("candidate_solution -> goal must use answers", invalid.stderr)
            self.assertIn("answers edge must connect candidate_solution -> goal", invalid.stderr)

    def test_validate_accepts_prompts_edge_for_follow_up_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "prompts-edge-state.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 0.6},
                    {"id": "T1", "type": "test", "text": "Check likely cause"},
                ],
                "edges": [{"from": "A1", "to": "T1", "type": "prompts"}],
                "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            valid = self.run_cli("validate", str(state_path))
            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertIn("ok", valid.stdout)

    def test_audit_uses_no_new_work_reason_for_score_only_visited_updates(self) -> None:
        base_state = {
            "nodes": [
                {"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 1.0},
                {"id": "T1", "type": "test", "text": "Check likely cause"},
                {"id": "D1", "type": "derived", "text": "A1 explored once"},
                {"id": "E2", "type": "evidence", "text": "Negative result", "confidence": 0.8},
            ],
            "edges": [
                {"id": "EA1D1", "from": "A1", "to": "D1", "type": "leads_to"},
                {"id": "ET1E2", "from": "T1", "to": "E2", "type": "supports"},
                {"id": "EE2A1", "from": "E2", "to": "A1", "type": "contradicts"},
            ],
            "frontier": [
                {"id": "Q1", "node": "A1"},
                {"id": "Q2", "node": "T1"},
            ],
            "events": [
                {"step": 1, "action": "init", "frontier": ["Q1", "Q2"]},
                {"step": 2, "action": "pop", "item": "Q1", "cost": 0.0},
                {"step": 3, "action": "expand", "item": "Q1", "add_nodes": ["D1"], "add_edges": ["EA1D1"], "add_frontier": []},
                {"step": 4, "action": "pop", "item": "Q2", "cost": 0.0},
                {
                    "step": 5,
                    "action": "expand",
                    "item": "Q2",
                    "add_nodes": ["E2"],
                    "add_edges": ["ET1E2", "EE2A1"],
                    "add_frontier": [],
                    "updated_nodes": [{"id": "A1", "fields": ["truth_cost"]}],
                    "no_new_work_reason": "E2 only changes A1 score; no new A1-local work implied.",
                },
                {"step": 6, "action": "stop", "reason": "test stop", "outcome": "user_stopped"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            ok_path = Path(tmp_dir) / "ok.json"
            missing_path = Path(tmp_dir) / "missing.json"
            ok_path.write_text(json.dumps(base_state), encoding="utf-8")
            missing_state = json.loads(json.dumps(base_state))
            del missing_state["events"][4]["no_new_work_reason"]
            missing_path.write_text(json.dumps(missing_state), encoding="utf-8")

            ok = self.run_cli("audit", str(ok_path))
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertNotIn("evidence updated visited node", ok.stderr)

            missing = self.run_cli("audit", str(missing_path))
            self.assertEqual(missing.returncode, 0, missing.stderr)
            self.assertIn("evidence updated visited node A1", missing.stderr)
            self.assertIn("no_new_work_reason", missing.stderr)

    def test_costs_use_conditional_likelihood_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "likelihood-state.json"
            output_path = Path(tmp_dir) / "likelihood-output.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 0.5},
                    {"id": "E1", "type": "evidence", "text": "Positive signal"},
                    {"id": "E2", "type": "evidence", "text": "Negative signal"},
                ],
                "edges": [
                    {"from": "E1", "to": "A1", "type": "supports", "likelihood": {"if_target_true": 0.75, "if_target_false": 0.25}},
                    {"from": "E2", "to": "A1", "type": "contradicts", "likelihood": {"if_target_true": 0.2, "if_target_false": 0.4}},
                ],
                "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = self.run_cli("costs", str(state_path), "-o", str(output_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            costed = json.loads(output_path.read_text(encoding="utf-8"))
            # Prior odds 1 * (0.75/0.25) * (0.2/0.4) = odds 1.5 => posterior 0.6 => -ln(.6).
            self.assertAlmostEqual(costed["frontier"][0]["truth_cost"], 0.510826, places=6)

    def test_costs_use_likelihood_ratio_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "lr-state.json"
            output_path = Path(tmp_dir) / "lr-output.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 0.5},
                    {"id": "E1", "type": "evidence", "text": "Positive signal"},
                    {"id": "E2", "type": "evidence", "text": "Negative signal"},
                ],
                "edges": [
                    {"from": "E1", "to": "A1", "type": "supports", "likelihood_ratio": 3.0},
                    {"from": "E2", "to": "A1", "type": "contradicts", "likelihood_ratio": 0.5},
                ],
                "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = self.run_cli("costs", str(state_path), "-o", str(output_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            costed = json.loads(output_path.read_text(encoding="utf-8"))
            # Prior odds 1 * LR 3 * LR 0.5 = odds 1.5 => posterior 0.6 => -ln(.6).
            self.assertAlmostEqual(costed["frontier"][0]["truth_cost"], 0.510826, places=6)

    def test_search_cursor_does_not_mutate_frontier_costs(self) -> None:
        state = {
            "nodes": [{"id": "A1", "type": "assumption", "text": "Premise A", "prior": 0.5}],
            "edges": [],
            "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
        }
        original = json.loads(json.dumps(state))

        cursor = search_cursor(state)

        self.assertEqual(cursor["active_ids"], {"Q1"})
        self.assertEqual(state, original)

    def test_search_cursor_applies_supersede_events(self) -> None:
        state = {
            "nodes": [{"id": "A1", "type": "assumption", "text": "Shared work", "prior": 1.0}],
            "edges": [],
            "frontier": [
                {"id": "Q1", "node": "A1", "cost_components": {"truth": "auto", "verification": 0.1}},
                {"id": "Q2", "node": "A1", "cost_components": {"truth": "auto", "verification": 0.5}},
            ],
            "events": [
                {"step": 1, "action": "init", "frontier": ["Q1", "Q2"]},
                {
                    "step": 2,
                    "action": "supersede",
                    "item": "Q2",
                    "replacement": "Q1",
                    "reason": "duplicate expansion_signature; kept lower latest search_cost",
                },
            ],
        }

        cursor = search_cursor(state)

        self.assertEqual(cursor["active_ids"], {"Q1"})

    def test_audit_rejects_equal_cost_supersede(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "equal-cost-supersede.json"
            state = {
                "nodes": [{"id": "A1", "type": "assumption", "text": "Shared work", "prior": 1.0}],
                "edges": [],
                "frontier": [
                    {"id": "Q1", "node": "A1", "cost_components": {"truth": "auto", "verification": 0.1}},
                    {"id": "Q2", "node": "A1", "cost_components": {"truth": "auto", "verification": 0.1}},
                ],
                "events": [
                    {"step": 1, "action": "init", "frontier": ["Q1", "Q2"]},
                    {
                        "step": 2,
                        "action": "supersede",
                        "item": "Q1",
                        "replacement": "Q2",
                        "reason": "duplicate expansion_signature",
                    },
                    {"step": 3, "action": "stop", "reason": "manual stop", "outcome": "user_stopped"},
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = self.run_cli("audit", str(state_path))

            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("must be lower than superseded item", result.stderr)

    def test_next_initializes_deduped_frontier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Shared work", "prior": 1.0},
                    {"id": "A2", "type": "assumption", "text": "Other work", "prior": 1.0},
                ],
                "edges": [],
                "frontier": [
                    {"id": "Q1", "node": "A1", "cost_components": {"truth": "auto", "verification": 0.5}},
                    {"id": "Q2", "node": "A1", "cost_components": {"truth": "auto", "verification": 0.1}},
                    {"id": "Q3", "node": "A2", "cost_components": {"truth": "auto", "verification": 0.2}},
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = self.run_cli("next", str(state_path), "--pop", "-i")
            self.assertEqual(result.returncode, 0, result.stderr)
            updated = json.loads(state_path.read_text(encoding="utf-8"))

            self.assertEqual(updated["events"][0], {"step": 1, "action": "init", "frontier": ["Q2", "Q3"]})
            self.assertEqual(updated["events"][1]["action"], "pop")
            self.assertEqual(updated["events"][1]["item"], "Q2")

    def test_assign_records_async_probe_and_allows_next_pop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            state = {
                "search_policy": {"max_probe_concurrency": 2},
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "First probe", "prior": 1.0},
                    {"id": "A2", "type": "assumption", "text": "Second probe", "prior": 1.0},
                ],
                "edges": [],
                "frontier": [
                    {"id": "Q1", "node": "A1", "cost_components": {"truth": "auto", "verification": 0.1}},
                    {"id": "Q2", "node": "A2", "cost_components": {"truth": "auto", "verification": 0.2}},
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            first_pop = self.run_cli("next", str(state_path), "--pop", "-i")
            self.assertEqual(first_pop.returncode, 0, first_pop.stderr)
            assigned = self.run_cli(
                "assign",
                str(state_path),
                "--item",
                "Q1",
                "--agent",
                "researcher",
                "--run-id",
                "child-1",
                "-i",
            )
            self.assertEqual(assigned.returncode, 0, assigned.stderr)
            updated = json.loads(state_path.read_text(encoding="utf-8"))
            cursor = search_cursor(updated)
            self.assertIsNone(cursor["pending_item"])
            self.assertEqual(cursor["in_flight_ids"], {"Q1"})
            self.assertEqual(cursor["active_ids"], {"Q2"})

            second_pop = self.run_cli("next", str(state_path), "--pop", "-i")
            self.assertEqual(second_pop.returncode, 0, second_pop.stderr)
            updated = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual([event["action"] for event in updated["events"]], ["init", "pop", "assign", "pop"])
            self.assertEqual(updated["events"][2]["agent"], "researcher")
            self.assertEqual(updated["events"][2]["run_id"], "child-1")
            self.assertEqual(updated["events"][3]["item"], "Q2")

    def test_assign_enforces_max_probe_concurrency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "First probe", "prior": 1.0},
                    {"id": "A2", "type": "assumption", "text": "Second probe", "prior": 1.0},
                ],
                "edges": [],
                "frontier": [
                    {"id": "Q1", "node": "A1", "cost_components": {"truth": "auto", "verification": 0.1}},
                    {"id": "Q2", "node": "A2", "cost_components": {"truth": "auto", "verification": 0.2}},
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            self.assertEqual(self.run_cli("next", str(state_path), "--pop", "-i").returncode, 0)
            self.assertEqual(self.run_cli("assign", str(state_path), "--item", "Q1", "--max-concurrency", "1", "-i").returncode, 0)
            self.assertEqual(self.run_cli("next", str(state_path), "--pop", "-i").returncode, 0)
            over_limit = self.run_cli("assign", str(state_path), "--item", "Q2", "--max-concurrency", "1", "-i")

            self.assertNotEqual(over_limit.returncode, 0)
            self.assertIn("max probe concurrency reached", over_limit.stderr)

    def test_expand_can_merge_assigned_probe_out_of_pop_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            patch_q1_path = Path(tmp_dir) / "patch-q1.json"
            patch_q2_path = Path(tmp_dir) / "patch-q2.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Async probe", "prior": 1.0},
                    {"id": "A2", "type": "assumption", "text": "Inline probe", "prior": 1.0},
                ],
                "edges": [],
                "frontier": [
                    {"id": "Q1", "node": "A1", "cost_components": {"truth": "auto", "verification": 0.1}},
                    {"id": "Q2", "node": "A2", "cost_components": {"truth": "auto", "verification": 0.2}},
                ],
            }
            patch_q1_path.write_text(json.dumps({"no_new_work_reason": "delegated probe completed without new evidence"}), encoding="utf-8")
            patch_q2_path.write_text(json.dumps({"no_new_work_reason": "inline probe closed"}), encoding="utf-8")
            state_path.write_text(json.dumps(state), encoding="utf-8")

            self.assertEqual(self.run_cli("next", str(state_path), "--pop", "-i").returncode, 0)
            self.assertEqual(self.run_cli("assign", str(state_path), "--item", "Q1", "--agent", "researcher", "-i").returncode, 0)
            self.assertEqual(self.run_cli("next", str(state_path), "--pop", "-i").returncode, 0)
            expand_q2 = self.run_cli("expand", str(state_path), "--item", "Q2", "--patch", str(patch_q2_path), "-i")
            self.assertEqual(expand_q2.returncode, 0, expand_q2.stderr)
            expand_q1 = self.run_cli("expand", str(state_path), "--item", "Q1", "--patch", str(patch_q1_path), "-i")
            self.assertEqual(expand_q1.returncode, 0, expand_q1.stderr)
            audit = self.run_cli("stop", str(state_path), "--reason", "done", "--outcome", "frontier_exhausted", "-i")
            self.assertEqual(audit.returncode, 0, audit.stderr)
            audit = self.run_cli("audit", str(state_path))

            self.assertEqual(audit.returncode, 0, audit.stderr)
            updated = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(search_cursor(updated)["in_flight_ids"], set())
            self.assertEqual([event["action"] for event in updated["events"]], ["init", "pop", "assign", "pop", "expand", "expand", "stop"])

    def test_stop_rejects_unresolved_in_flight_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            state = {
                "nodes": [{"id": "A1", "type": "assumption", "text": "Async probe", "prior": 1.0}],
                "edges": [],
                "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            self.assertEqual(self.run_cli("next", str(state_path), "--pop", "-i").returncode, 0)
            self.assertEqual(self.run_cli("assign", str(state_path), "--item", "Q1", "-i").returncode, 0)
            stopped = self.run_cli("stop", str(state_path), "--reason", "done", "--outcome", "user_stopped", "-i")

            self.assertNotEqual(stopped.returncode, 0)
            self.assertIn("assigned items remain in-flight", stopped.stderr)

    def test_expand_patch_stop_rejects_other_in_flight_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            patch_path = Path(tmp_dir) / "patch.json"
            state = {
                "search_policy": {"max_probe_concurrency": 2},
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "First async probe", "prior": 1.0},
                    {"id": "A2", "type": "assumption", "text": "Second async probe", "prior": 1.0},
                ],
                "edges": [],
                "frontier": [
                    {"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}},
                    {"id": "Q2", "node": "A2", "cost_components": {"truth": "auto", "verification": 0.1}},
                ],
            }
            patch = {
                "no_new_work_reason": "first probe complete",
                "stop_reason": "done",
                "stop_outcome": "frontier_exhausted",
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            patch_path.write_text(json.dumps(patch), encoding="utf-8")

            self.assertEqual(self.run_cli("next", str(state_path), "--pop", "-i").returncode, 0)
            self.assertEqual(self.run_cli("assign", str(state_path), "--item", "Q1", "-i").returncode, 0)
            self.assertEqual(self.run_cli("next", str(state_path), "--pop", "-i").returncode, 0)
            self.assertEqual(self.run_cli("assign", str(state_path), "--item", "Q2", "-i").returncode, 0)
            stopped = self.run_cli("expand", str(state_path), "--item", "Q1", "--patch", str(patch_path), "-i")

            self.assertNotEqual(stopped.returncode, 0)
            self.assertIn("assigned items remain in-flight", stopped.stderr)
            updated = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertNotEqual(updated["events"][-1]["action"], "stop")

    def test_audit_enforces_policy_max_probe_concurrency_without_event_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            state = {
                "search_policy": {"max_probe_concurrency": 1},
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "First", "prior": 1.0},
                    {"id": "A2", "type": "assumption", "text": "Second", "prior": 1.0},
                ],
                "edges": [],
                "frontier": [
                    {"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}},
                    {"id": "Q2", "node": "A2", "cost_components": {"truth": "auto", "verification": 0.1}},
                ],
                "events": [
                    {"step": 1, "action": "init", "frontier": ["Q1", "Q2"]},
                    {"step": 2, "action": "pop", "item": "Q1", "cost": 0.0},
                    {"step": 3, "action": "assign", "item": "Q1"},
                    {"step": 4, "action": "pop", "item": "Q2", "cost": 0.1},
                    {"step": 5, "action": "assign", "item": "Q2"},
                    {"step": 6, "action": "stop", "reason": "done", "outcome": "frontier_exhausted"},
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            audit = self.run_cli("audit", str(state_path))

            self.assertNotEqual(audit.returncode, 0)
            self.assertIn("max probe concurrency exceeded (2/1)", audit.stderr)

    def test_audit_rejects_stop_with_unresolved_assigned_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            state = {
                "nodes": [{"id": "A1", "type": "assumption", "text": "Async probe", "prior": 1.0}],
                "edges": [],
                "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
                "events": [
                    {"step": 1, "action": "init", "frontier": ["Q1"]},
                    {"step": 2, "action": "pop", "item": "Q1", "cost": 0.0},
                    {"step": 3, "action": "assign", "item": "Q1", "max_concurrency": 2},
                    {"step": 4, "action": "stop", "reason": "done", "outcome": "frontier_exhausted"},
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            audit = self.run_cli("audit", str(state_path))

            self.assertNotEqual(audit.returncode, 0)
            self.assertIn("assigned items remain in-flight", audit.stderr)

    def test_audit_rejects_second_pop_before_treating_pending_item(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "First", "prior": 1.0},
                    {"id": "A2", "type": "assumption", "text": "Second", "prior": 1.0},
                ],
                "edges": [],
                "frontier": [
                    {"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}},
                    {"id": "Q2", "node": "A2", "cost_components": {"truth": "auto", "verification": 0.1}},
                ],
                "events": [
                    {"step": 1, "action": "init", "frontier": ["Q1", "Q2"]},
                    {"step": 2, "action": "pop", "item": "Q1", "cost": 0.0},
                    {"step": 3, "action": "pop", "item": "Q2", "cost": 0.1},
                    {"step": 4, "action": "stop", "reason": "done", "outcome": "frontier_exhausted"},
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            audit = self.run_cli("audit", str(state_path))

            self.assertNotEqual(audit.returncode, 0)
            self.assertIn("cannot pop while unresolved popped item Q1 is pending", audit.stderr)

    def test_audit_rejects_pop_that_skipped_cheaper_item_before_direct_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "direct-cost-update-out-of-order.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "First branch", "prior": 0.5},
                    {"id": "A2", "type": "assumption", "text": "Second branch", "prior": 0.5},
                    {"id": "E1", "type": "evidence", "text": "Later contradiction"},
                ],
                "edges": [
                    {"id": "E1A2", "from": "E1", "to": "A2", "type": "contradicts", "likelihood_ratio": 0.01},
                ],
                "frontier": [
                    {"id": "Q1", "node": "A1", "cost_components": {"truth": "auto", "verification": 0.1}},
                    {"id": "Q2", "node": "A2", "cost_components": {"truth": "auto"}},
                ],
                "events": [
                    {"step": 1, "action": "init", "frontier": ["Q1", "Q2"]},
                    {"step": 2, "action": "pop", "item": "Q1", "cost": 0.793147},
                    {
                        "step": 3,
                        "action": "expand",
                        "item": "Q1",
                        "add_nodes": [],
                        "add_edges": ["E1A2"],
                        "add_frontier": [],
                        "no_new_work_reason": "Evidence was recorded for later review; no child work added.",
                    },
                    {"step": 4, "action": "stop", "reason": "manual stop", "outcome": "user_stopped"},
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            audit = self.run_cli("audit", str(state_path))

            self.assertNotEqual(audit.returncode, 0, audit.stdout)
            self.assertIn("lowest frontier search_cost", audit.stderr)

    def test_audit_accepts_best_first_pop_after_direct_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "direct-cost-update-in-order.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "First branch", "prior": 0.5},
                    {"id": "A2", "type": "assumption", "text": "Second branch", "prior": 0.5},
                    {"id": "E1", "type": "evidence", "text": "Later contradiction"},
                ],
                "edges": [
                    {"id": "E1A1", "from": "E1", "to": "A1", "type": "contradicts", "likelihood_ratio": 0.01},
                ],
                "frontier": [
                    {"id": "Q1", "node": "A1", "cost_components": {"truth": "auto", "verification": 0.1}},
                    {"id": "Q2", "node": "A2", "cost_components": {"truth": "auto"}},
                ],
                "events": [
                    {"step": 1, "action": "init", "frontier": ["Q1", "Q2"]},
                    {"step": 2, "action": "pop", "item": "Q2", "cost": 0.693147},
                    {
                        "step": 3,
                        "action": "expand",
                        "item": "Q2",
                        "add_nodes": [],
                        "add_edges": ["E1A1"],
                        "add_frontier": [],
                        "no_new_work_reason": "Evidence changed Q1 priority but created no new work.",
                    },
                    {"step": 4, "action": "pop", "item": "Q1", "cost": 4.715121},
                    {
                        "step": 5,
                        "action": "expand",
                        "item": "Q1",
                        "add_nodes": [],
                        "add_edges": [],
                        "add_frontier": [],
                        "no_new_work_reason": "Branch complete.",
                    },
                    {"step": 6, "action": "stop", "reason": "manual stop", "outcome": "user_stopped"},
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            audit = self.run_cli("audit", str(state_path))

            self.assertEqual(audit.returncode, 0, audit.stderr)

    def test_audit_rejects_pop_that_skipped_cheaper_item_before_transitive_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "transitive-cost-update-out-of-order.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "First premise", "prior": 0.5},
                    {"id": "A2", "type": "assumption", "text": "Second premise", "prior": 0.5},
                    {"id": "D1", "type": "derived", "text": "First derived branch"},
                    {"id": "D2", "type": "derived", "text": "Second derived branch"},
                    {"id": "E1", "type": "evidence", "text": "Later contradiction"},
                ],
                "edges": [
                    {"id": "A1D1", "from": "A1", "to": "D1", "type": "leads_to"},
                    {"id": "A2D2", "from": "A2", "to": "D2", "type": "leads_to"},
                    {"id": "E1A1", "from": "E1", "to": "A1", "type": "contradicts", "likelihood_ratio": 0.01},
                ],
                "frontier": [
                    {"id": "Q1", "node": "D1", "cost_components": {"truth": "auto", "verification": 0.1}},
                    {"id": "Q2", "node": "D2", "cost_components": {"truth": "auto", "verification": 0.2}},
                ],
                "events": [
                    {"step": 1, "action": "init", "frontier": ["Q1", "Q2"]},
                    {"step": 2, "action": "pop", "item": "Q2", "cost": 0.893147},
                    {
                        "step": 3,
                        "action": "expand",
                        "item": "Q2",
                        "add_nodes": [],
                        "add_edges": ["E1A1"],
                        "add_frontier": [],
                        "no_new_work_reason": "Evidence was recorded for later review; no child work added.",
                    },
                    {"step": 4, "action": "stop", "reason": "manual stop", "outcome": "user_stopped"},
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            audit = self.run_cli("audit", str(state_path))

            self.assertNotEqual(audit.returncode, 0, audit.stdout)
            self.assertIn("lowest frontier search_cost", audit.stderr)

    def test_audit_accepts_best_first_pop_after_transitive_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "transitive-cost-update-in-order.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "First premise", "prior": 0.5},
                    {"id": "A2", "type": "assumption", "text": "Second premise", "prior": 0.5},
                    {"id": "D1", "type": "derived", "text": "First derived branch"},
                    {"id": "D2", "type": "derived", "text": "Second derived branch"},
                    {"id": "E1", "type": "evidence", "text": "Later contradiction"},
                ],
                "edges": [
                    {"id": "A1D1", "from": "A1", "to": "D1", "type": "leads_to"},
                    {"id": "A2D2", "from": "A2", "to": "D2", "type": "leads_to"},
                    {"id": "E1A2", "from": "E1", "to": "A2", "type": "contradicts", "likelihood_ratio": 0.01},
                ],
                "frontier": [
                    {"id": "Q1", "node": "D1", "cost_components": {"truth": "auto", "verification": 0.1}},
                    {"id": "Q2", "node": "D2", "cost_components": {"truth": "auto", "verification": 0.2}},
                ],
                "events": [
                    {"step": 1, "action": "init", "frontier": ["Q1", "Q2"]},
                    {"step": 2, "action": "pop", "item": "Q1", "cost": 0.793147},
                    {
                        "step": 3,
                        "action": "expand",
                        "item": "Q1",
                        "add_nodes": [],
                        "add_edges": ["E1A2"],
                        "add_frontier": [],
                        "no_new_work_reason": "Evidence changed Q2 priority but created no new work.",
                    },
                    {"step": 4, "action": "pop", "item": "Q2", "cost": 4.815121},
                    {
                        "step": 5,
                        "action": "expand",
                        "item": "Q2",
                        "add_nodes": [],
                        "add_edges": [],
                        "add_frontier": [],
                        "no_new_work_reason": "Branch complete.",
                    },
                    {"step": 6, "action": "stop", "reason": "manual stop", "outcome": "user_stopped"},
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            audit = self.run_cli("audit", str(state_path))

            self.assertEqual(audit.returncode, 0, audit.stderr)

    def test_expand_supersedes_existing_duplicate_when_new_item_is_cheaper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            patch_path = Path(tmp_dir) / "patch.json"
            state = {
                "nodes": [
                    {"id": "A0", "type": "assumption", "text": "Start", "prior": 1.0},
                    {"id": "A1", "type": "assumption", "text": "Shared next work", "prior": 1.0},
                ],
                "edges": [],
                "frontier": [
                    {"id": "Q0", "node": "A0", "cost_components": {"truth": "auto"}},
                    {"id": "Q1", "node": "A1", "cost_components": {"truth": "auto", "verification": 0.5}},
                ],
                "events": [
                    {"step": 1, "action": "init", "frontier": ["Q0", "Q1"]},
                    {"step": 2, "action": "pop", "item": "Q0", "cost": 0.0},
                ],
            }
            patch = {
                "frontier": [
                    {"id": "Q2", "node": "A1", "cost_components": {"truth": "auto", "verification": 0.1}}
                ]
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            patch_path.write_text(json.dumps(patch), encoding="utf-8")

            result = self.run_cli("expand", str(state_path), "--item", "Q0", "--patch", str(patch_path), "-i")
            self.assertEqual(result.returncode, 0, result.stderr)
            updated = json.loads(state_path.read_text(encoding="utf-8"))

            self.assertIn("Q2", {item["id"] for item in updated["frontier"]})
            self.assertEqual(updated["events"][-2]["action"], "expand")
            self.assertEqual(updated["events"][-2]["add_frontier"], ["Q2"])
            self.assertEqual(updated["events"][-1]["action"], "supersede")
            self.assertEqual(updated["events"][-1]["item"], "Q1")
            self.assertEqual(updated["events"][-1]["replacement"], "Q2")
            self.assertEqual(search_cursor(updated)["active_ids"], {"Q2"})

    def test_expand_skips_new_duplicate_when_existing_item_is_cheaper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            patch_path = Path(tmp_dir) / "patch.json"
            state = {
                "nodes": [
                    {"id": "A0", "type": "assumption", "text": "Start", "prior": 1.0},
                    {"id": "A1", "type": "assumption", "text": "Shared next work", "prior": 1.0},
                ],
                "edges": [],
                "frontier": [
                    {"id": "Q0", "node": "A0", "cost_components": {"truth": "auto"}},
                    {"id": "Q1", "node": "A1", "cost_components": {"truth": "auto", "verification": 0.1}},
                ],
                "events": [
                    {"step": 1, "action": "init", "frontier": ["Q0", "Q1"]},
                    {"step": 2, "action": "pop", "item": "Q0", "cost": 0.0},
                ],
            }
            patch = {
                "frontier": [
                    {"id": "Q2", "node": "A1", "cost_components": {"truth": "auto", "verification": 0.5}}
                ]
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            patch_path.write_text(json.dumps(patch), encoding="utf-8")

            result = self.run_cli("expand", str(state_path), "--item", "Q0", "--patch", str(patch_path), "-i")
            self.assertEqual(result.returncode, 0, result.stderr)
            updated = json.loads(state_path.read_text(encoding="utf-8"))

            self.assertNotIn("Q2", {item["id"] for item in updated["frontier"]})
            self.assertEqual(updated["events"][-1]["action"], "expand")
            self.assertEqual(updated["events"][-1]["add_frontier"], [])
            self.assertEqual(search_cursor(updated)["active_ids"], {"Q1"})

    def test_costs_include_estimated_remaining_cost_as_frontier_heuristic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "remaining-cost-state.json"
            output_path = Path(tmp_dir) / "remaining-cost-output.json"
            state = {
                "search_policy": {"estimated_remaining_weight": 0.5},
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Cheap but far", "prior": 1.0},
                    {"id": "A2", "type": "assumption", "text": "Expensive but near", "prior": 1.0},
                ],
                "edges": [],
                "frontier": [
                    {
                        "id": "Q1",
                        "node": "A1",
                        "cost_components": {"truth": "auto", "verification": 0.1},
                        "estimated_remaining_cost": 2.0,
                    },
                    {
                        "id": "Q2",
                        "node": "A2",
                        "cost_components": {"truth": "auto", "verification": 1.0},
                        "estimated_remaining_cost": 0.0,
                    },
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = self.run_cli("sort", str(state_path), "-o", str(output_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            costed = json.loads(output_path.read_text(encoding="utf-8"))
            by_id = {item["id"]: item for item in costed["frontier"]}
            self.assertEqual([item["id"] for item in costed["frontier"]], ["Q2", "Q1"])
            self.assertAlmostEqual(by_id["Q1"]["base_search_cost"], 0.1, places=6)
            self.assertAlmostEqual(by_id["Q1"]["heuristic_cost"], 1.0, places=6)
            self.assertAlmostEqual(by_id["Q1"]["search_cost"], 1.1, places=6)
            self.assertAlmostEqual(by_id["Q2"]["search_cost"], 1.0, places=6)

    def test_costs_reject_misplaced_estimated_remaining_cost_component(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "misplaced-distance-field.json"
            state = {
                "nodes": [{"id": "A1", "type": "assumption", "text": "Branch", "prior": 1.0}],
                "edges": [],
                "frontier": [
                    {
                        "id": "Q1",
                        "node": "A1",
                        "cost_components": {"truth": "auto", "estimated_remaining_cost": 0.75},
                    }
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = self.run_cli("validate", str(state_path))
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("cost_components.estimated_remaining_cost must be top-level", result.stderr)

    def test_costs_reject_invalid_estimated_remaining_cost(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "invalid-distance.json"
            state = {
                "nodes": [{"id": "A1", "type": "assumption", "text": "Branch", "prior": 1.0}],
                "edges": [],
                "frontier": [
                    {
                        "id": "Q1",
                        "node": "A1",
                        "cost_components": {"truth": "auto"},
                        "estimated_remaining_cost": -0.1,
                    }
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = self.run_cli("costs", str(state_path))
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("estimated_remaining_cost must be finite and non-negative", result.stderr)

    def test_costs_reject_invalid_estimated_remaining_weight(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "invalid-weight.json"
            state = {
                "search_policy": {"estimated_remaining_weight": -1},
                "nodes": [{"id": "A1", "type": "assumption", "text": "Branch", "prior": 1.0}],
                "edges": [],
                "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = self.run_cli("costs", str(state_path))
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertIn("search_policy.estimated_remaining_weight must be finite and non-negative", result.stderr)

    def test_costs_propagate_leads_to_premises_without_parent_double_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "premise-state.json"
            output_path = Path(tmp_dir) / "premise-output.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Premise A", "prior": 0.8},
                    {"id": "E1", "type": "evidence", "text": "Premise E", "confidence": 0.9},
                    {"id": "D1", "type": "derived", "text": "Derived from A and E"},
                ],
                "edges": [
                    {"from": "A1", "to": "D1", "type": "leads_to"},
                    {"from": "E1", "to": "D1", "type": "leads_to"},
                ],
                "frontier": [
                    {"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}},
                    {"id": "Q2", "node": "D1", "parent": "Q1", "cost_components": {"truth": "auto"}},
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = self.run_cli("costs", str(state_path), "-o", str(output_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            costed = json.loads(output_path.read_text(encoding="utf-8"))
            by_id = {item["id"]: item for item in costed["frontier"]}
            self.assertAlmostEqual(by_id["Q1"]["truth_cost"], 0.223144, places=6)
            # D1 truth is graph-derived from both premises; parent chain is audit context, not probability accumulation.
            self.assertAlmostEqual(by_id["Q2"]["step_truth_cost"], 0.328504, places=6)
            self.assertAlmostEqual(by_id["Q2"]["truth_cost"], 0.328504, places=6)

    def test_costs_factor_replaces_correlated_likelihood_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "factor-likelihood-state.json"
            output_path = Path(tmp_dir) / "factor-likelihood-output.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 0.5},
                    {"id": "E1", "type": "evidence", "text": "Positive signal A"},
                    {"id": "E2", "type": "evidence", "text": "Positive signal B"},
                    {"id": "E3", "type": "evidence", "text": "Independent signal"},
                ],
                "edges": [
                    {"from": "E1", "to": "A1", "type": "supports", "likelihood": {"if_target_true": 0.8, "if_target_false": 0.2}},
                    {"from": "E2", "to": "A1", "type": "supports", "likelihood": {"if_target_true": 0.9, "if_target_false": 0.3}},
                    {"from": "E3", "to": "A1", "type": "supports", "likelihood": {"if_target_true": 0.6, "if_target_false": 0.3}},
                ],
                "factors": [
                    {
                        "id": "F1",
                        "relation": "supports",
                        "inputs": ["E1", "E2"],
                        "target": "A1",
                        "aggregation": {"kind": "likelihood", "if_target_true": 0.6, "if_target_false": 0.2},
                        "reason": "E1 and E2 are correlated, so their combined LR is calibrated directly.",
                    }
                ],
                "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = self.run_cli("costs", str(state_path), "-o", str(output_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            costed = json.loads(output_path.read_text(encoding="utf-8"))
            # Prior odds 1 * grouped LR 3 * independent LR 2 = odds 6 => posterior 6/7 => -ln(6/7).
            self.assertAlmostEqual(costed["frontier"][0]["truth_cost"], 0.154151, places=6)

            valid = self.run_cli("validate", str(state_path))
            self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_costs_leads_to_factor_replaces_independent_member_costs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "factor-leads-to-state.json"
            output_path = Path(tmp_dir) / "factor-leads-to-output.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Premise A", "prior": 0.2},
                    {"id": "B1", "type": "evidence", "text": "Premise B", "confidence": 0.3},
                    {"id": "C1", "type": "assumption", "text": "Independent premise C", "prior": 0.5},
                    {"id": "D1", "type": "derived", "text": "Derived from A, B, and C"},
                ],
                "edges": [
                    {"from": "A1", "to": "D1", "type": "leads_to"},
                    {"from": "B1", "to": "D1", "type": "leads_to"},
                    {"from": "C1", "to": "D1", "type": "leads_to"},
                ],
                "factors": [
                    {
                        "id": "F1",
                        "relation": "leads_to",
                        "inputs": ["A1", "B1"],
                        "target": "D1",
                        "aggregation": {"kind": "joint_probability", "probability": 0.18},
                        "reason": "A1 and B1 share a latent source.",
                    }
                ],
                "frontier": [{"id": "Q1", "node": "D1", "cost_components": {"truth": "auto"}}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = self.run_cli("costs", str(state_path), "-o", str(output_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            costed = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertAlmostEqual(costed["frontier"][0]["truth_cost"], 2.407946, places=6)

            valid = self.run_cli("validate", str(state_path))
            self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_validate_rejects_raw_leads_to_cycle_even_when_grouped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "grouped-cycle-state.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Premise A", "prior": 0.5},
                    {"id": "B1", "type": "assumption", "text": "Premise B", "prior": 0.5},
                    {"id": "D1", "type": "derived", "text": "Derived claim"},
                ],
                "edges": [
                    {"from": "A1", "to": "D1", "type": "leads_to"},
                    {"from": "B1", "to": "D1", "type": "leads_to"},
                    {"from": "D1", "to": "A1", "type": "leads_to"},
                ],
                "factors": [
                    {
                        "id": "F1",
                        "relation": "leads_to",
                        "target": "D1",
                        "inputs": ["A1", "B1"],
                        "aggregation": {"kind": "joint_probability", "probability": 0.4},
                        "reason": "Factor cost must not hide the raw cycle.",
                    }
                ],
                "frontier": [{"id": "Q1", "node": "D1", "cost_components": {"truth": "auto"}}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            invalid = self.run_cli("validate", str(state_path))
            self.assertNotEqual(invalid.returncode, 0, invalid.stdout)
            self.assertIn("cycle in truth dependency graph", invalid.stderr)

    def test_validate_warns_but_accepts_missing_factor_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "missing-reason-factor-state.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Premise A", "prior": 0.8},
                    {"id": "B1", "type": "assumption", "text": "Premise B", "prior": 0.8},
                    {"id": "D1", "type": "derived", "text": "Derived claim"},
                ],
                "edges": [
                    {"from": "A1", "to": "D1", "type": "leads_to"},
                    {"from": "B1", "to": "D1", "type": "leads_to"},
                ],
                "factors": [
                    {
                        "id": "F1",
                        "relation": "leads_to",
                        "target": "D1",
                        "inputs": ["A1", "B1"],
                        "aggregation": {"kind": "joint_probability", "probability": 0.7},
                    }
                ],
                "frontier": [{"id": "Q1", "node": "D1", "cost_components": {"truth": "auto"}}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            valid = self.run_cli("validate", str(state_path))
            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertIn("should include reason", valid.stderr)

    def test_expand_patch_upserts_new_factors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "expand-factor-state.json"
            patch_path = Path(tmp_dir) / "expand-factor-patch.json"
            output_path = Path(tmp_dir) / "expand-factor-output.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 0.5},
                    {"id": "E1", "type": "evidence", "text": "Positive signal A"},
                    {"id": "E2", "type": "evidence", "text": "Positive signal B"},
                ],
                "edges": [{"id": "E1A", "from": "E1", "to": "A1", "type": "supports", "likelihood": {"if_target_true": 0.8, "if_target_false": 0.2}}],
                "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
            }
            patch = {
                "edges": [{"id": "E2A", "from": "E2", "to": "A1", "type": "supports", "likelihood": {"if_target_true": 0.9, "if_target_false": 0.3}}],
                "factors": [
                    {
                        "id": "F1",
                        "relation": "supports",
                        "inputs": ["E1", "E2"],
                        "target": "A1",
                        "aggregation": {"kind": "likelihood", "if_target_true": 0.6, "if_target_false": 0.2},
                        "reason": "E1 and E2 share source.",
                    }
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            patch_path.write_text(json.dumps(patch), encoding="utf-8")

            result = self.run_cli(
                "expand", str(state_path), "--item", "Q1", "--patch", str(patch_path), "--force", "-o", str(output_path)
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            expanded = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(expanded["factors"][0]["id"], "F1")
            self.assertEqual(expanded["events"][-1]["update_factors"], ["F1"])
            self.assertEqual(expanded["events"][-1]["updated_factor_snapshots"][0]["before"], None)
            self.assertAlmostEqual(expanded["frontier"][0]["truth_cost"], 0.287682, places=6)

    def test_audit_accepts_updated_factors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "audit-factor-state.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 0.5},
                    {"id": "E1", "type": "evidence", "text": "Positive signal A"},
                    {"id": "E2", "type": "evidence", "text": "Positive signal B"},
                ],
                "edges": [
                    {"id": "E1A", "from": "E1", "to": "A1", "type": "supports", "likelihood": {"if_target_true": 0.8, "if_target_false": 0.2}},
                    {"id": "E2A", "from": "E2", "to": "A1", "type": "supports", "likelihood": {"if_target_true": 0.9, "if_target_false": 0.3}},
                ],
                "factors": [
                    {
                        "id": "F1",
                        "relation": "supports",
                        "inputs": ["E1", "E2"],
                        "target": "A1",
                        "aggregation": {"kind": "likelihood", "if_target_true": 0.6, "if_target_false": 0.2},
                        "reason": "E1 and E2 share source.",
                    }
                ],
                "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
                "events": [
                    {"step": 1, "action": "init", "frontier": ["Q1"]},
                    {"step": 2, "action": "pop", "item": "Q1", "cost": 0.287682},
                    {
                        "step": 3,
                        "action": "expand",
                        "item": "Q1",
                        "add_nodes": [],
                        "add_edges": ["E2A"],
                        "add_frontier": [],
                        "update_factors": ["F1"],
                        "no_new_work_reason": "Calibration only.",
                    },
                    {"step": 4, "action": "stop", "reason": "done", "outcome": "frontier_exhausted"},
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = self.run_cli("audit", str(state_path))
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_costs_explicit_posterior_overrides_graph_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "posterior-state.json"
            output_path = Path(tmp_dir) / "posterior-output.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 0.2, "posterior": 0.7},
                    {"id": "E1", "type": "evidence", "text": "Negative signal"},
                ],
                "edges": [{"from": "E1", "to": "A1", "type": "contradicts", "likelihood_ratio": 0.1}],
                "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = self.run_cli("costs", str(state_path), "-o", str(output_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            costed = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertAlmostEqual(costed["frontier"][0]["truth_cost"], 0.356675, places=6)

    def test_costs_do_not_subtract_unrelated_parent_truth(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "unrelated-parent-state.json"
            output_path = Path(tmp_dir) / "unrelated-parent-output.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Required premise", "prior": 0.5},
                    {"id": "B1", "type": "assumption", "text": "Audit parent only", "prior": 0.5},
                    {"id": "D1", "type": "derived", "text": "Derived from A"},
                ],
                "edges": [{"from": "A1", "to": "D1", "type": "leads_to"}],
                "frontier": [
                    {"id": "Q1", "node": "B1", "cost_components": {"truth": "auto"}},
                    {"id": "Q2", "node": "D1", "parent": "Q1", "cost_components": {"truth": "auto"}},
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = self.run_cli("costs", str(state_path), "-o", str(output_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            costed = json.loads(output_path.read_text(encoding="utf-8"))
            by_id = {item["id"]: item for item in costed["frontier"]}
            self.assertNotIn("path_cost", by_id["Q1"])
            self.assertAlmostEqual(by_id["Q1"]["truth_cost"], 0.693147, places=6)
            self.assertAlmostEqual(by_id["Q2"]["truth_cost"], 0.693147, places=6)
            self.assertAlmostEqual(by_id["Q2"]["search_cost"], 0.693147, places=6)

    def test_contradicts_without_likelihood_ratio_is_explanatory_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "legacy-contradiction-state.json"
            output_path = Path(tmp_dir) / "legacy-contradiction-output.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 0.5},
                    {"id": "E1", "type": "evidence", "text": "Negative signal", "confidence": 0.1},
                ],
                "edges": [{"from": "E1", "to": "A1", "type": "contradicts", "strength": 1.0}],
                "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = self.run_cli("costs", str(state_path), "-o", str(output_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            costed = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertAlmostEqual(costed["frontier"][0]["truth_cost"], 0.693147, places=6)

            valid = self.run_cli("validate", str(state_path))
            self.assertNotEqual(valid.returncode, 0, valid.stdout)
            self.assertIn("ignored legacy field(s) strength", valid.stderr)
            self.assertIn("schema $.edges[0]", valid.stderr)

    def test_validate_rejects_bad_likelihood_ratio_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "bad-lr-state.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 0.5},
                    {"id": "E1", "type": "evidence", "text": "Signal"},
                ],
                "edges": [
                    {"from": "E1", "to": "A1", "type": "supports", "likelihood_ratio": 0.5},
                    {"from": "A1", "to": "E1", "type": "leads_to", "likelihood_ratio": 2.0},
                    {
                        "from": "E1",
                        "to": "A1",
                        "type": "supports",
                        "likelihood_ratio": 2.0,
                        "likelihood": {"if_target_true": 0.8, "if_target_false": 0.2},
                    },
                    {"from": "E1", "to": "A1", "type": "contradicts", "likelihood": {"if_target_true": 0.8, "if_target_false": 0.2}},
                ],
                "frontier": [],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            invalid = self.run_cli("validate", str(state_path))
            self.assertNotEqual(invalid.returncode, 0, invalid.stdout)
            self.assertIn("supports likelihood ratio must be > 1", invalid.stderr)
            self.assertIn("likelihood/likelihood_ratio is only valid on supports/contradicts", invalid.stderr)
            self.assertIn("edge must not set both likelihood and likelihood_ratio", invalid.stderr)
            self.assertIn("contradicts likelihood ratio must be in (0, 1)", invalid.stderr)

    def test_validate_rejects_bad_factors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "bad-factors.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 0.5},
                    {"id": "E1", "type": "evidence", "text": "Signal A"},
                    {"id": "E2", "type": "evidence", "text": "Signal B"},
                    {"id": "E3", "type": "evidence", "text": "Signal C"},
                ],
                "edges": [
                    {"from": "E1", "to": "A1", "type": "supports"},
                    {"from": "E2", "to": "A1", "type": "supports"},
                ],
                "factors": [
                    {
                        "id": "F1",
                        "relation": "supports",
                        "inputs": ["E1", "E2"],
                        "target": "A1",
                        "aggregation": {"kind": "likelihood", "if_target_true": 0.2, "if_target_false": 0.8},
                        "likelihood_ratio": 2.0,
                        "reason": "wrong direction and direct ratio forbidden",
                    },
                    {
                        "id": "F2",
                        "relation": "supports",
                        "inputs": ["E2", "E3"],
                        "target": "A1",
                        "aggregation": {"kind": "joint_probability", "probability": 0.5},
                        "reason": "overlaps and E3 has no support edge",
                    },
                ],
                "frontier": [],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            invalid = self.run_cli("validate", str(state_path))
            self.assertNotEqual(invalid.returncode, 0, invalid.stdout)
            self.assertIn("factors[0] must not set likelihood_ratio directly", invalid.stderr)
            self.assertIn("factors[0] supports likelihood ratio must be > 1", invalid.stderr)
            self.assertIn("factors[1] input 'E3' must have a supports edge to target 'A1'", invalid.stderr)
            self.assertIn("supports factors for target 'A1' overlap on input(s) E2", invalid.stderr)
            self.assertIn("factors[1].aggregation.kind must be 'likelihood' for supports/contradicts factors", invalid.stderr)

    def test_costs_writes_computed_frontier_costs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "costs.json"
            result = self.run_cli("costs", str(FIXTURE), "-o", str(output))

            self.assertEqual(result.returncode, 0, result.stderr)
            state = json.loads(output.read_text(encoding="utf-8"))
            frontier = state["frontier"]
            self.assertTrue(frontier)
            self.assertTrue(all("search_cost" in item for item in frontier))
            self.assertTrue(all("truth_cost" in item for item in frontier))

    def test_stop_output_does_not_mutate_input_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            stopped_path = Path(tmp_dir) / "stopped.json"
            original = FIXTURE.read_text(encoding="utf-8")
            state_path.write_text(original, encoding="utf-8")

            result = self.run_cli(
                "stop",
                str(state_path),
                "--reason",
                "test stop",
                "--outcome",
                "user_stopped",
                "-o",
                str(stopped_path),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original)
            stopped = json.loads(stopped_path.read_text(encoding="utf-8"))
            self.assertEqual(stopped["events"][-1]["action"], "stop")
            self.assertEqual(stopped["events"][-1]["outcome"], "user_stopped")

    def test_expand_patch_with_ranked_candidate_stop_does_not_duplicate_rank(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            patch_path = Path(tmp_dir) / "patch.json"
            state = json.loads(FIXTURE.read_text(encoding="utf-8"))
            state["events"] = [event for event in state["events"] if event.get("action") not in {"rank", "stop"}]
            patch = {
                "rank": True,
                "no_new_work_reason": "candidate already supported; closing pending item",
                "stop_reason": "CS1 answers G1 and sample frontier is complete",
                "stop_outcome": "solved",
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            patch_path.write_text(json.dumps(patch), encoding="utf-8")

            result = self.run_cli("expand", str(state_path), "--item", "Q3", "--patch", str(patch_path), "-i")

            self.assertEqual(result.returncode, 0, result.stderr)
            updated = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual([event["action"] for event in updated["events"][-3:]], ["expand", "rank", "stop"])
            self.assertEqual(sum(1 for event in updated["events"] if event.get("action") == "rank"), 1)

    def test_stop_ranks_candidate_outcomes_without_mutating_input_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            stopped_path = Path(tmp_dir) / "stopped.json"
            state = json.loads(FIXTURE.read_text(encoding="utf-8"))
            state["events"] = [event for event in state["events"] if event.get("action") not in {"rank", "stop"}]
            original = json.dumps(state, indent=2) + "\n"
            state_path.write_text(original, encoding="utf-8")

            result = self.run_cli(
                "stop",
                str(state_path),
                "--reason",
                "CS1 answers G1 and sample frontier is complete",
                "--outcome",
                "solved",
                "-o",
                str(stopped_path),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original)
            stopped = json.loads(stopped_path.read_text(encoding="utf-8"))
            self.assertEqual([event["action"] for event in stopped["events"][-2:]], ["rank", "stop"])
            self.assertEqual(stopped["events"][-2]["best"], "CS1")
            self.assertEqual(stopped["events"][-1]["outcome"], "solved")

            audit = self.run_cli("audit", str(stopped_path))
            self.assertEqual(audit.returncode, 0, audit.stderr)

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
            self.assertIn("Best explanation graph", html_text)
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

    def test_mermaid_and_html_render_virtual_factors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "factor-render-state.json"
            html_path = Path(tmp_dir) / "factor-render.html"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 0.5},
                    {"id": "E1", "type": "evidence", "text": "Positive signal A"},
                    {"id": "E2", "type": "evidence", "text": "Positive signal B"},
                ],
                "edges": [
                    {"from": "E1", "to": "A1", "type": "supports"},
                    {"from": "E2", "to": "A1", "type": "supports"},
                ],
                "factors": [
                    {
                        "id": "F1",
                        "relation": "supports",
                        "inputs": ["E1", "E2"],
                        "target": "A1",
                        "aggregation": {"kind": "likelihood", "if_target_true": 0.6, "if_target_false": 0.2},
                        "reason": "E1 and E2 share source.",
                    }
                ],
                "frontier": [],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            mermaid = self.run_cli("mermaid", str(state_path))
            self.assertEqual(mermaid.returncode, 0, mermaid.stderr)
            self.assertIn("F1", mermaid.stdout)
            self.assertIn("grouped supports", mermaid.stdout)
            self.assertIn("supports factor", mermaid.stdout)

            html = self.run_cli("html", str(state_path), "--offline", "-o", str(html_path))
            self.assertEqual(html.returncode, 0, html.stderr)
            html_text = html_path.read_text(encoding="utf-8")
            self.assertIn("F1", html_text)
            self.assertIn("grouped supports", html_text)
            self.assertIn("supports factor", html_text)
            self.assertNotIn("https://cdn.jsdelivr.net", html_text)


if __name__ == "__main__":
    unittest.main()
