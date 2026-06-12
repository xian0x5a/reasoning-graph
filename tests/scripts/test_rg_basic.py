import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RG = REPO_ROOT / "skills" / "reasoning-graph" / "scripts" / "rg.py"
FIXTURE = REPO_ROOT / "tests" / "reasoning-graph-strict-good.json"


class ReasoningGraphCliBasicTests(unittest.TestCase):
    def run_rg(self, *args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(RG), *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            **kwargs,
        )

    def test_validate_and_audit_fixture_pass(self) -> None:
        validate = self.run_rg("validate", str(FIXTURE))
        self.assertEqual(validate.returncode, 0, validate.stderr)
        self.assertIn("ok", validate.stdout)

        audit = self.run_rg("audit", str(FIXTURE))
        self.assertEqual(audit.returncode, 0, audit.stderr)
        self.assertIn("ok", audit.stdout)

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
            # D1 requires A1 and E1; Q2 parent already carries A1, so step adds only E1.
            self.assertAlmostEqual(by_id["Q2"]["step_truth_cost"], 0.105361, places=6)
            self.assertAlmostEqual(by_id["Q2"]["truth_cost"], 0.328504, places=6)

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
                ],
                "frontier": [],
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")

            invalid = self.run_rg("validate", str(state_path))
            self.assertNotEqual(invalid.returncode, 0, invalid.stdout)
            self.assertIn("supports likelihood_ratio must be > 1", invalid.stderr)
            self.assertIn("likelihood_ratio is only valid on supports/contradicts", invalid.stderr)

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


if __name__ == "__main__":
    unittest.main()
