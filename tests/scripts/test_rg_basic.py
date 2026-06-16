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
SKILL_SRC_ROOT = REPO_ROOT / "skills" / "reasoning-graph" / "src"
sys.path.insert(0, str(SKILL_SRC_ROOT))

from reasoning_graph.frontier import search_cursor


FIXTURE = REPO_ROOT / "tests" / "reasoning-graph-strict-good.json"
STATE_SCHEMA = REPO_ROOT / "skills" / "reasoning-graph" / "src" / "reasoning_graph" / "schemas" / "state.schema.json"
PATCH_SCHEMA = REPO_ROOT / "skills" / "reasoning-graph" / "src" / "reasoning_graph" / "schemas" / "patch.schema.json"


class ReasoningGraphCliBasicTests(unittest.TestCase):
    def run_rg(self, *args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["uv", "run", "rg", *args],
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

    @unittest.skipIf(jsonschema is None, "jsonschema not installed")
    def test_json_schema_validates_fixture_and_patch_examples(self) -> None:
        state_schema = json.loads(STATE_SCHEMA.read_text(encoding="utf-8"))
        patch_schema = json.loads(PATCH_SCHEMA.read_text(encoding="utf-8"))
        fixture_state = json.loads(FIXTURE.read_text(encoding="utf-8"))
        patch = {
            "nodes": [{"id": "A3", "type": "assumption", "text": "Third cause", "prior": 0.2}],
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

    def test_template_and_init_emit_valid_starter_states(self) -> None:
        template = self.run_rg("template", "benchmark")
        self.assertEqual(template.returncode, 0, template.stderr)
        template_state = json.loads(template.stdout)
        self.assertEqual(template_state["nodes"][0]["id"], "G1")
        self.assertEqual(template_state["stop_policy"]["severity"], "error")
        self.assertEqual(template_state["branch_policy"]["enforce_on"], "always")

        init = self.run_rg("init", "--goal", "Diagnose production outage", "--strict")
        self.assertEqual(init.returncode, 0, init.stderr)
        init_state = json.loads(init.stdout)
        self.assertEqual(init_state["nodes"][0]["text"], "Diagnose production outage")
        self.assertEqual(init_state["stop_policy"]["severity"], "error")

        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "starter.json"
            state_path.write_text(template.stdout, encoding="utf-8")
            valid = self.run_rg("validate", str(state_path))
            self.assertEqual(valid.returncode, 0, valid.stderr)

    def test_stop_review_passes_fixture_and_fails_missing_viable_candidate(self) -> None:
        ok = self.run_rg("stop-review", str(FIXTURE))
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("verdict: pass", ok.stdout)
        self.assertIn("best candidate answers an accepted goal", ok.stdout)

        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "missing-candidate.json"
            state = json.loads(FIXTURE.read_text(encoding="utf-8"))
            state["edges"] = [edge for edge in state["edges"] if edge.get("type") != "answers"]
            state_path.write_text(json.dumps(state), encoding="utf-8")

            missing = self.run_rg("stop-review", str(state_path))
            self.assertNotEqual(missing.returncode, 0, missing.stdout)
            self.assertIn("verdict: fail", missing.stdout)
            self.assertIn("requires a viable candidate_solution", missing.stdout)

    def test_stop_review_compares_optional_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            draft_path = Path(tmp_dir) / "answer.md"
            draft_path.write_text("Candidate from A1 is the answer.", encoding="utf-8")
            ok = self.run_rg("stop-review", str(FIXTURE), "--draft", str(draft_path), "--strict-warnings")
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertIn("verdict: pass", ok.stdout)

            draft_path.write_text("Unrelated answer.", encoding="utf-8")
            missing = self.run_rg("stop-review", str(FIXTURE), "--draft", str(draft_path), "--strict-warnings")
            self.assertNotEqual(missing.returncode, 0, missing.stdout)
            self.assertIn("draft does not mention best candidate", missing.stdout)

    def test_doctor_reports_validation_and_audit_health(self) -> None:
        ok = self.run_rg("doctor", str(FIXTURE))
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("doctor: validation ok", ok.stdout)
        self.assertIn("doctor: audit ok", ok.stdout)

        with tempfile.TemporaryDirectory() as tmp_dir:
            invalid_path = Path(tmp_dir) / "invalid.json"
            invalid_path.write_text(json.dumps({"nodes": [{"id": "X1", "type": "fact"}]}), encoding="utf-8")
            invalid = self.run_rg("doctor", str(invalid_path))
            self.assertNotEqual(invalid.returncode, 0, invalid.stdout)
            self.assertIn("invalid type 'fact'", invalid.stderr)
            self.assertIn("doctor: validation failed", invalid.stdout)

    def test_validate_and_audit_fixture_pass(self) -> None:
        validate = self.run_rg("validate", str(FIXTURE))
        self.assertEqual(validate.returncode, 0, validate.stderr)
        self.assertIn("ok", validate.stdout)

        audit = self.run_rg("audit", str(FIXTURE))
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

            audit = self.run_rg("audit", str(state_path))

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

            valid = self.run_rg("validate", str(state_path))
            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertIn("ok", valid.stdout)

            invalid = self.run_rg("validate", str(legacy_path))
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

            invalid = self.run_rg("validate", str(invalid_path))
            self.assertNotEqual(invalid.returncode, 0, invalid.stdout)
            self.assertIn("candidate_solution -> goal must use answers", invalid.stderr)
            self.assertIn("answers edge must connect candidate_solution -> goal", invalid.stderr)

    def test_validate_accepts_prompts_edge_for_follow_up_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "prompts-edge-state.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 0.6},
                    {"id": "T1", "type": "test", "text": "Check likely cause", "status": "proposed"},
                ],
                "edges": [{"from": "A1", "to": "T1", "type": "prompts"}],
                "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            valid = self.run_rg("validate", str(state_path))
            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertIn("ok", valid.stdout)

    def test_audit_uses_no_new_work_reason_for_score_only_visited_updates(self) -> None:
        base_state = {
            "nodes": [
                {"id": "A1", "type": "assumption", "text": "Likely cause", "prior": 1.0},
                {"id": "T1", "type": "test", "text": "Check likely cause", "status": "performed"},
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

            ok = self.run_rg("audit", str(ok_path))
            self.assertEqual(ok.returncode, 0, ok.stderr)
            self.assertNotIn("evidence updated visited node", ok.stderr)

            missing = self.run_rg("audit", str(missing_path))
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

            result = self.run_rg("costs", str(state_path), "-o", str(output_path))
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

            result = self.run_rg("costs", str(state_path), "-o", str(output_path))
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

            result = self.run_rg("audit", str(state_path))

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

            result = self.run_rg("next", str(state_path), "--pop", "-i")
            self.assertEqual(result.returncode, 0, result.stderr)
            updated = json.loads(state_path.read_text(encoding="utf-8"))

            self.assertEqual(updated["events"][0], {"step": 1, "action": "init", "frontier": ["Q2", "Q3"]})
            self.assertEqual(updated["events"][1]["action"], "pop")
            self.assertEqual(updated["events"][1]["item"], "Q2")

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

            result = self.run_rg("expand", str(state_path), "--item", "Q0", "--patch", str(patch_path), "-i")
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

            result = self.run_rg("expand", str(state_path), "--item", "Q0", "--patch", str(patch_path), "-i")
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

            result = self.run_rg("sort", str(state_path), "-o", str(output_path))
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

            result = self.run_rg("validate", str(state_path))
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

            result = self.run_rg("costs", str(state_path))
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

            result = self.run_rg("costs", str(state_path))
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

            result = self.run_rg("costs", str(state_path), "-o", str(output_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            costed = json.loads(output_path.read_text(encoding="utf-8"))
            by_id = {item["id"]: item for item in costed["frontier"]}
            self.assertAlmostEqual(by_id["Q1"]["truth_cost"], 0.223144, places=6)
            # D1 truth is graph-derived from both premises; parent chain is audit context, not probability accumulation.
            self.assertAlmostEqual(by_id["Q2"]["step_truth_cost"], 0.328504, places=6)
            self.assertAlmostEqual(by_id["Q2"]["truth_cost"], 0.328504, places=6)

    def test_costs_premise_group_replaces_independent_member_costs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "premise-group-state.json"
            output_path = Path(tmp_dir) / "premise-group-output.json"
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
                "premise_groups": [
                    {
                        "id": "PG1",
                        "target": "D1",
                        "premises": ["A1", "B1"],
                        "joint_probability": 0.18,
                        "reason": "A1 and B1 share a latent source, so their costs should not be multiplied independently.",
                    }
                ],
                "frontier": [{"id": "Q1", "node": "D1", "cost_components": {"truth": "auto"}}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = self.run_rg("costs", str(state_path), "-o", str(output_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            costed = json.loads(output_path.read_text(encoding="utf-8"))
            # Group cost -ln(.18) replaces A1/B1 member costs; C1 remains independent: -ln(.18) + -ln(.5).
            self.assertAlmostEqual(costed["frontier"][0]["truth_cost"], 2.407946, places=6)

            valid = self.run_rg("validate", str(state_path))
            self.assertEqual(valid.returncode, 0, valid.stderr)

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

            result = self.run_rg("costs", str(state_path), "-o", str(output_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            costed = json.loads(output_path.read_text(encoding="utf-8"))
            # Prior odds 1 * grouped LR 3 * independent LR 2 = odds 6 => posterior 6/7 => -ln(6/7).
            self.assertAlmostEqual(costed["frontier"][0]["truth_cost"], 0.154151, places=6)

            valid = self.run_rg("validate", str(state_path))
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

            result = self.run_rg("costs", str(state_path), "-o", str(output_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            costed = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertAlmostEqual(costed["frontier"][0]["truth_cost"], 2.407946, places=6)

            valid = self.run_rg("validate", str(state_path))
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
                "premise_groups": [
                    {
                        "id": "PG1",
                        "target": "D1",
                        "premises": ["A1", "B1"],
                        "joint_probability": 0.4,
                        "reason": "Group cost must not hide the raw cycle.",
                    }
                ],
                "frontier": [{"id": "Q1", "node": "D1", "cost_components": {"truth": "auto"}}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            invalid = self.run_rg("validate", str(state_path))
            self.assertNotEqual(invalid.returncode, 0, invalid.stdout)
            self.assertIn("cycle in truth dependency graph", invalid.stderr)

    def test_validate_warns_but_accepts_missing_premise_group_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "missing-reason-premise-group-state.json"
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
                "premise_groups": [{"id": "PG1", "target": "D1", "premises": ["A1", "B1"], "joint_probability": 0.7}],
                "frontier": [{"id": "Q1", "node": "D1", "cost_components": {"truth": "auto"}}],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            valid = self.run_rg("validate", str(state_path))
            self.assertEqual(valid.returncode, 0, valid.stderr)
            self.assertIn("should include reason", valid.stderr)

    def test_expand_patch_upserts_new_premise_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "expand-premise-group-state.json"
            patch_path = Path(tmp_dir) / "expand-premise-group-patch.json"
            output_path = Path(tmp_dir) / "expand-premise-group-output.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Premise A", "prior": 0.2},
                    {"id": "B1", "type": "evidence", "text": "Premise B", "confidence": 0.3},
                    {"id": "D1", "type": "derived", "text": "Derived claim"},
                ],
                "edges": [{"id": "EAD", "from": "A1", "to": "D1", "type": "leads_to"}],
                "frontier": [{"id": "Q1", "node": "D1", "cost_components": {"truth": "auto"}}],
            }
            patch = {
                "edges": [{"id": "EBD", "from": "B1", "to": "D1", "type": "leads_to"}],
                "update_premise_groups": [
                    {
                        "id": "PG1",
                        "target": "D1",
                        "premises": ["A1", "B1"],
                        "joint_probability": 0.18,
                        "reason": "A1 and B1 share a latent source.",
                    }
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            patch_path.write_text(json.dumps(patch), encoding="utf-8")

            result = self.run_rg(
                "expand", str(state_path), "--item", "Q1", "--patch", str(patch_path), "--force", "-o", str(output_path)
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            expanded = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(expanded["premise_groups"][0]["id"], "PG1")
            self.assertEqual(expanded["events"][-1]["update_premise_groups"], ["PG1"])
            self.assertAlmostEqual(expanded["frontier"][0]["truth_cost"], 1.714798, places=6)

    def test_expand_patch_updates_existing_premise_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "update-premise-group-state.json"
            patch_path = Path(tmp_dir) / "update-premise-group-patch.json"
            output_path = Path(tmp_dir) / "update-premise-group-output.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Premise A", "prior": 0.2},
                    {"id": "B1", "type": "evidence", "text": "Premise B", "confidence": 0.3},
                    {"id": "C1", "type": "assumption", "text": "Premise C", "prior": 0.5},
                    {"id": "D1", "type": "derived", "text": "Derived claim"},
                ],
                "edges": [
                    {"id": "EAD", "from": "A1", "to": "D1", "type": "leads_to"},
                    {"id": "EBD", "from": "B1", "to": "D1", "type": "leads_to"},
                ],
                "premise_groups": [
                    {
                        "id": "PG1",
                        "target": "D1",
                        "premises": ["A1", "B1"],
                        "joint_probability": 0.18,
                        "reason": "Initial two-premise calibration.",
                    }
                ],
                "frontier": [{"id": "Q1", "node": "D1", "cost_components": {"truth": "auto"}}],
            }
            patch = {
                "edges": [{"id": "ECD", "from": "C1", "to": "D1", "type": "leads_to"}],
                "update_premise_groups": [
                    {
                        "id": "PG1",
                        "target": "D1",
                        "premises": ["A1", "B1", "C1"],
                        "joint_probability": 0.09,
                        "reason": "A1, B1, and C1 share a latent source.",
                    }
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            patch_path.write_text(json.dumps(patch), encoding="utf-8")

            result = self.run_rg(
                "expand", str(state_path), "--item", "Q1", "--patch", str(patch_path), "--force", "-o", str(output_path)
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            expanded = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(len(expanded["premise_groups"]), 1)
            self.assertEqual(expanded["premise_groups"][0]["premises"], ["A1", "B1", "C1"])
            self.assertEqual(expanded["events"][-1]["update_premise_groups"], ["PG1"])
            self.assertAlmostEqual(expanded["frontier"][0]["truth_cost"], 2.407946, places=6)

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
                "update_factors": [
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

            result = self.run_rg(
                "expand", str(state_path), "--item", "Q1", "--patch", str(patch_path), "--force", "-o", str(output_path)
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            expanded = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(expanded["factors"][0]["id"], "F1")
            self.assertEqual(expanded["events"][-1]["update_factors"], ["F1"])
            self.assertAlmostEqual(expanded["frontier"][0]["truth_cost"], 0.287682, places=6)

    def test_audit_accepts_updated_premise_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "audit-premise-group-state.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Premise A", "prior": 0.2},
                    {"id": "B1", "type": "evidence", "text": "Premise B", "confidence": 0.3},
                    {"id": "D1", "type": "derived", "text": "Derived claim"},
                ],
                "edges": [
                    {"id": "EAD", "from": "A1", "to": "D1", "type": "leads_to"},
                    {"id": "EBD", "from": "B1", "to": "D1", "type": "leads_to"},
                ],
                "premise_groups": [
                    {
                        "id": "PG1",
                        "target": "D1",
                        "premises": ["A1", "B1"],
                        "joint_probability": 0.18,
                        "reason": "A1 and B1 share a latent source.",
                    }
                ],
                "frontier": [{"id": "Q1", "node": "D1", "cost_components": {"truth": "auto"}}],
                "events": [
                    {"step": 1, "action": "init", "frontier": ["Q1"]},
                    {"step": 2, "action": "pop", "item": "Q1", "cost": 1.714798},
                    {
                        "step": 3,
                        "action": "expand",
                        "item": "Q1",
                        "add_nodes": [],
                        "add_edges": ["EBD"],
                        "add_frontier": [],
                        "update_premise_groups": ["PG1"],
                        "no_new_work_reason": "Calibration only.",
                    },
                    {"step": 4, "action": "stop", "reason": "done", "outcome": "frontier_exhausted"},
                ],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = self.run_rg("audit", str(state_path))
            self.assertEqual(result.returncode, 0, result.stderr)

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

            result = self.run_rg("audit", str(state_path))
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

            result = self.run_rg("costs", str(state_path), "-o", str(output_path))
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

            result = self.run_rg("costs", str(state_path), "-o", str(output_path))
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

            result = self.run_rg("costs", str(state_path), "-o", str(output_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            costed = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertAlmostEqual(costed["frontier"][0]["truth_cost"], 0.693147, places=6)

            valid = self.run_rg("validate", str(state_path))
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

            invalid = self.run_rg("validate", str(state_path))
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

            invalid = self.run_rg("validate", str(state_path))
            self.assertNotEqual(invalid.returncode, 0, invalid.stdout)
            self.assertIn("factors[0] must not set likelihood_ratio directly", invalid.stderr)
            self.assertIn("factors[0] supports likelihood ratio must be > 1", invalid.stderr)
            self.assertIn("factors[1] input 'E3' must have a supports edge to target 'A1'", invalid.stderr)
            self.assertIn("supports factors for target 'A1' overlap on input(s) E2", invalid.stderr)
            self.assertIn("factors[1].aggregation.kind must be 'likelihood' for supports/contradicts factors", invalid.stderr)

    def test_validate_rejects_bad_premise_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "bad-premise-groups.json"
            state = {
                "nodes": [
                    {"id": "A1", "type": "assumption", "text": "Premise A", "prior": 0.5},
                    {"id": "B1", "type": "assumption", "text": "Premise B", "prior": 0.5},
                    {"id": "C1", "type": "assumption", "text": "Premise C", "prior": 0.5},
                    {"id": "D1", "type": "derived", "text": "Derived claim"},
                ],
                "edges": [
                    {"from": "A1", "to": "D1", "type": "leads_to"},
                    {"from": "B1", "to": "D1", "type": "leads_to"},
                ],
                "premise_groups": [
                    {
                        "id": "PG1",
                        "target": "D1",
                        "premises": ["A1", "B1"],
                        "joint_probability": 0.8,
                        "effective_truth_cost": 0.2,
                        "reason": "same source",
                    },
                    {
                        "id": "PG2",
                        "target": "D1",
                        "premises": ["B1", "C1"],
                        "joint_probability": 0.0,
                        "reason": "overlaps and lacks C1 dependency",
                    },
                    {"id": "PG3", "target": "D1", "premises": ["A1"], "joint_probability": 0.5},
                ],
                "frontier": [],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            invalid = self.run_rg("validate", str(state_path))
            self.assertNotEqual(invalid.returncode, 0, invalid.stdout)
            self.assertIn("premise_groups[0] must not set effective_truth_cost", invalid.stderr)
            self.assertIn("premise_groups[1] premise 'C1' must have a leads_to edge to target 'D1'", invalid.stderr)
            self.assertIn("premise_groups for target 'D1' overlap on premise(s) B1", invalid.stderr)
            self.assertIn("premise_groups[1].joint_probability must be in (0, 1]", invalid.stderr)
            self.assertIn("premise_groups[2].premises must be a list of at least two node ids", invalid.stderr)

    def test_costs_writes_computed_frontier_costs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "costs.json"
            result = self.run_rg("costs", str(FIXTURE), "-o", str(output))

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

            result = self.run_rg(
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

    def test_finalize_ranks_then_stops_without_mutating_input_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            stopped_path = Path(tmp_dir) / "stopped.json"
            state = json.loads(FIXTURE.read_text(encoding="utf-8"))
            state["events"] = [event for event in state["events"] if event.get("action") not in {"rank", "stop"}]
            original = json.dumps(state, indent=2) + "\n"
            state_path.write_text(original, encoding="utf-8")

            result = self.run_rg(
                "finalize",
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

            audit = self.run_rg("audit", str(stopped_path))
            self.assertEqual(audit.returncode, 0, audit.stderr)

    def test_mermaid_and_html_smoke(self) -> None:
        mermaid = self.run_rg("mermaid", str(FIXTURE))
        self.assertEqual(mermaid.returncode, 0, mermaid.stderr)
        self.assertIn("flowchart", mermaid.stdout)

        with tempfile.TemporaryDirectory() as tmp_dir:
            html_path = Path(tmp_dir) / "graph.html"
            html = self.run_rg("html", str(FIXTURE), "-o", str(html_path))
            self.assertEqual(html.returncode, 0, html.stderr)
            html_text = html_path.read_text(encoding="utf-8")
            self.assertIn("<!doctype html>", html_text.lower())
            self.assertIn("Best explanation graph", html_text)

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

            mermaid = self.run_rg("mermaid", str(state_path))
            self.assertEqual(mermaid.returncode, 0, mermaid.stderr)
            self.assertIn("F1", mermaid.stdout)
            self.assertIn("grouped supports", mermaid.stdout)
            self.assertIn("supports factor", mermaid.stdout)

            html = self.run_rg("html", str(state_path), "-o", str(html_path))
            self.assertEqual(html.returncode, 0, html.stderr)
            html_text = html_path.read_text(encoding="utf-8")
            self.assertIn("F1", html_text)
            self.assertIn("grouped supports", html_text)
            self.assertIn("supports factor", html_text)


if __name__ == "__main__":
    unittest.main()
