"""Edge identity, candidate answer_kind, patch field, and presentation reference contracts
(#12, #17, #16, #10)."""

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
            {"id": "A1", "type": "assumption", "text": "Likely route", "prior": 0.6},
            {"id": "A2", "type": "assumption", "text": "Other route", "prior": 0.3},
            {"id": "CS1", "type": "candidate_solution", "text": "Answer one", "answer_kind": "exact_answer", "prior": 0.5},
        ],
        "edges": [
            {"id": "A1-CS1", "from": "A1", "to": "CS1", "type": "leads_to", "reasoning": "The candidate depends on the likely route."},
            {"id": "CS1-G1", "from": "CS1", "to": "G1", "type": "answers", "reasoning": "The candidate supplies the requested answer."},
        ],
        "frontier": [{"id": "Q1", "node": "A1", "cost_components": {"truth": "auto"}}],
    }


class ContractAlignmentTests(unittest.TestCase):
    def validate(self, state: dict) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            return run_cli("validate", str(state_path))

    def expand(self, patch: dict) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            patch_path = Path(tmp_dir) / "patch.json"
            state_path.write_text(json.dumps(base_state()), encoding="utf-8")
            popped = run_cli("next", str(state_path), "--pop")
            self.assertEqual(popped.returncode, 0, popped.stderr)
            patch_path.write_text(json.dumps(patch), encoding="utf-8")
            return run_cli("expand", str(state_path), "--item", "Q1", "--patch", str(patch_path))

    # --- #12 edge identity ---

    def test_edges_require_ids_in_state_and_patches(self) -> None:
        state = base_state()
        del state["edges"][0]["id"]
        result = self.validate(state)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("schema $.edges[0]: 'id' is a required property", result.stderr)

        patched = self.expand({"edges": [{"from": "A1", "to": "A2", "type": "supports", "reasoning": "Routes overlap."}]})
        self.assertEqual(patched.returncode, 1, patched.stdout)
        self.assertIn("$.edges[0]: 'id' is a required property", patched.stderr)

    def test_duplicate_edge_ids_are_rejected_before_mutation(self) -> None:
        state = base_state()
        state["edges"][1]["id"] = "A1-CS1"
        result = self.validate(state)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("duplicate edge id A1-CS1", result.stderr)

        patched = self.expand({"edges": [{"id": "A1-CS1", "from": "A1", "to": "A2", "type": "supports", "reasoning": "Routes overlap."}]})
        self.assertEqual(patched.returncode, 1, patched.stdout)
        self.assertIn("edges id A1-CS1 already exists", patched.stderr)

    # --- #17 answer_kind ---

    def test_candidate_without_answer_kind_is_rejected_regardless_of_policy(self) -> None:
        for policy in ({}, {"stop_policy": {"severity": "warning"}}, {"stop_policy": {"severity": "error"}}):
            with self.subTest(policy=policy):
                state = {**base_state(), **policy}
                del state["nodes"][3]["answer_kind"]
                result = self.validate(state)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("answer_kind", result.stderr)

        patched = self.expand({
            "nodes": [{"id": "CS2", "type": "candidate_solution", "text": "Answer two", "prior": 0.4}],
            "edges": [{"id": "CS2-G1", "from": "CS2", "to": "G1", "type": "answers", "reasoning": "Second candidate answers the goal."}],
        })
        self.assertEqual(patched.returncode, 1, patched.stdout)
        self.assertIn("answer_kind", patched.stderr)

    # --- #16 patch fields ---

    def test_patch_rejects_unimplemented_or_ambiguous_fields(self) -> None:
        factor = {
            "id": "F1",
            "relation": "supports",
            "inputs": ["A1", "A2"],
            "target": "CS1",
            "aggregation": {"kind": "likelihood", "if_target_true": 0.6, "if_target_false": 0.2},
            "reason": "Shared source.",
        }
        rejected_patches = {
            "outcome-alias": {"stop_reason": "done", "stop_outcome": "user_stopped", "outcome": "solved"},
            "factors-and-update-factors": {"factors": [factor], "update_factors": [factor]},
            "decorative-updated-nodes": {"updated_nodes": [{"id": "A1", "fields": ["prior"]}], "no_new_work_reason": "n/a"},
            "unknown-field": {"notes": "free text", "no_new_work_reason": "n/a"},
        }
        for label, patch in rejected_patches.items():
            with self.subTest(patch=label):
                result = self.expand(patch)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("error: schema $", result.stderr)

    def test_update_nodes_patch_field_is_recorded_in_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            patch_path = Path(tmp_dir) / "patch.json"
            state_path.write_text(json.dumps(base_state()), encoding="utf-8")
            self.assertEqual(run_cli("next", str(state_path), "--pop").returncode, 0)
            patch_path.write_text(
                json.dumps({"update_nodes": [{"id": "A1", "set": {"posterior": 0.7}}], "no_new_work_reason": "Calibration only."}),
                encoding="utf-8",
            )
            result = run_cli("expand", str(state_path), "--item", "Q1", "--patch", str(patch_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            event = json.loads(state_path.read_text(encoding="utf-8"))["events"][-1]
            self.assertEqual(event["updated_nodes"], [{"id": "A1", "fields": ["posterior"]}])

    # --- #10 presentation/view references ---

    def test_presentation_and_view_references_must_resolve(self) -> None:
        collections = {
            "presentation.include_nodes": ("presentation", "include_nodes"),
            "presentation.highlight_nodes": ("presentation", "highlight_nodes"),
            "presentation.dim_nodes": ("presentation", "dim_nodes"),
            "view.winning_path": ("view", "winning_path"),
            "view.dimmed_branches": ("view", "dimmed_branches"),
            "view.frontier": ("view", "frontier"),
        }
        for label, (section, key) in collections.items():
            with self.subTest(collection=label):
                state = base_state()
                state[section] = {key: ["A1", "MISSING"]}
                result = self.validate(state)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(f"{label}[1] references missing node 'MISSING'", result.stderr)

        state = base_state()
        state["presentation"] = {"include_nodes": ["A1", "CS1", "G1"], "highlight_nodes": ["CS1"], "dim_nodes": ["A1"]}
        state["view"] = {"winning_path": ["A1", "CS1", "G1"], "dimmed_branches": ["A2"], "frontier": ["A1"]}
        ok = self.validate(state)
        self.assertEqual(ok.returncode, 0, ok.stderr)

    def test_html_refuses_unresolved_presentation_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            state = base_state()
            state["presentation"] = {"include_nodes": ["MISSING"]}
            state_path.write_text(json.dumps(state), encoding="utf-8")
            result = run_cli("html", str(state_path), "-o", str(Path(tmp_dir) / "graph.html"))
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("presentation.include_nodes[0] references missing node 'MISSING'", result.stderr)


if __name__ == "__main__":
    unittest.main()
