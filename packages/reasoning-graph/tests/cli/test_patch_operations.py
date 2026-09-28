"""One record patch carries any graph edit, and a reason-only record re-syncs a hand-edited state.

In the #34 A/B, skill runs averaged 5.5 record calls and 1.5 Python hand-edits of state.json. A patch
could not change or remove an edge, remove a node or factor, or drop a field. A hand edit skipped the
quote check and left no event (issue #36 comment 5861985148)."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
SOURCE_TEXT = "The butler left at nine. The gardener stayed late, or so he said.\n"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )


def edge(source: str, target: str, edge_type: str, **extra: float) -> dict:
    return {"id": f"{source}-{target}", "from": source, "to": target, "type": edge_type, "reasoning": "Test edge.", **extra}


def observation(node_id: str, quote: str) -> dict:
    return {"id": node_id, "type": "observation", "text": quote, "source": "problem.md", "quote": quote, "prior": 0.9}


BASE_PATCH = {
    "reason": "Read the story",
    "nodes": [
        observation("O1", "The butler left at nine"),
        observation("O2", "The gardener stayed late, or so he said"),
        {"id": "H1", "type": "hypothesis", "text": "The gardener did it", "prior": 0.5},
        {"id": "H2", "type": "hypothesis", "text": "The butler did it", "prior": 0.3},
        {"id": "CS1", "type": "candidate_solution", "text": "The gardener", "answer_kind": "exact_answer", "prior": 0.9},
    ],
    "edges": [
        edge("O2", "H1", "supports", likelihood_ratio=3),
        edge("O1", "H1", "contradicts", likelihood_ratio=0.5),
        edge("O1", "H2", "supports", likelihood_ratio=2),
        edge("H1", "CS1", "leads_to"),
        edge("CS1", "G1", "answers"),
    ],
}


class PatchOperationTests(unittest.TestCase):
    def ok(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)

    def start(self, tmp_dir: str) -> Path:
        state_path = Path(tmp_dir) / "state.json"
        Path(tmp_dir, "problem.md").write_text(SOURCE_TEXT, encoding="utf-8")
        self.ok(run_cli("init", "--goal", "Who did it?", "--strict", "-o", str(state_path)))
        self.ok(self.record(state_path, BASE_PATCH))
        return state_path

    def record(self, state_path: Path, patch: dict) -> subprocess.CompletedProcess[str]:
        patch_path = state_path.with_name("patch.json")
        patch_path.write_text(json.dumps(patch), encoding="utf-8")
        return run_cli("record", str(state_path), "--patch", str(patch_path))

    def load(self, state_path: Path) -> dict:
        return json.loads(state_path.read_text(encoding="utf-8"))

    def hand_edit(self, state_path: Path, edit) -> None:
        state = self.load(state_path)
        edit(state)
        state_path.write_text(json.dumps(state), encoding="utf-8")

    def stop_and_audit(self, state_path: Path) -> subprocess.CompletedProcess[str]:
        self.ok(run_cli("stop", str(state_path), "--reason", "Test ends here", "--outcome", "inconclusive"))
        return run_cli("audit", str(state_path))

    def test_one_patch_updates_unsets_and_removes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)

            self.ok(self.record(state_path, {
                "reason": "Fold the review fixes into one patch",
                "update_nodes": [{"id": "CS1", "unset": ["prior"]}, {"id": "H1", "set": {"note": "Only his word"}}],
                "update_edges": [{"id": "O2-H1", "set": {"likelihood_ratio": 1.5}}, {"id": "O1-H1", "unset": ["likelihood_ratio"]}],
                "remove_nodes": ["H2"],
            }))

            state = self.load(state_path)
            nodes = {node["id"]: node for node in state["nodes"]}
            edges = {item["id"]: item for item in state["edges"]}
            self.assertNotIn("prior", nodes["CS1"])
            self.assertEqual(nodes["H1"]["note"], "Only his word")
            self.assertNotIn("H2", nodes)
            self.assertEqual(edges["O2-H1"]["likelihood_ratio"], 1.5)
            self.assertNotIn("likelihood_ratio", edges["O1-H1"])
            # Removing a node takes its edges with it.
            self.assertNotIn("O1-H2", edges)
            event = state["events"][-1]
            self.assertEqual(event["remove_nodes"], ["H2"])
            self.assertEqual(event["remove_edges"], ["O1-H2"])
            self.assertEqual(event["updated_nodes"], [{"id": "CS1", "fields": ["prior"]}, {"id": "H1", "fields": ["note"]}])
            self.assertEqual(event["updated_edges"], [{"id": "O2-H1", "fields": ["likelihood_ratio"]}, {"id": "O1-H1", "fields": ["likelihood_ratio"]}])
            self.ok(run_cli("validate", str(state_path)))

    def test_audit_accepts_an_object_removed_and_added_again(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)

            self.ok(self.record(state_path, {"reason": "Drop the weak link", "remove_edges": ["O1-H2"]}))
            self.ok(self.record(state_path, {"reason": "Restore it", "edges": [edge("O1", "H2", "supports", likelihood_ratio=1.5)]}))

            self.ok(self.stop_and_audit(state_path))

    def test_removing_a_factor_input_needs_the_factor_removed_too(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.ok(self.record(state_path, {
                "reason": "Both clues come from the gardener",
                "nodes": [observation("O3", "or so he said")],
                "edges": [edge("O3", "H1", "supports")],
                "update_edges": [{"id": "O2-H1", "unset": ["likelihood_ratio"]}],
                "factors": [{
                    "id": "F1", "relation": "supports", "target": "H1", "inputs": ["O2", "O3"],
                    "aggregation": {"kind": "likelihood", "if_target_true": 0.8, "if_target_false": 0.3},
                    "reason": "One witness.",
                }],
            }))
            before = state_path.read_text(encoding="utf-8")

            orphaned = self.record(state_path, {"reason": "Drop O3", "remove_nodes": ["O3"]})
            self.assertEqual(orphaned.returncode, 1, orphaned.stdout)
            self.assertIn("O3", orphaned.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

            self.ok(self.record(state_path, {"reason": "Drop O3 and its factor", "remove_nodes": ["O3"], "remove_factors": ["F1"]}))
            event = self.load(state_path)["events"][-1]
            self.assertEqual(event["remove_factors"], ["F1"])
            self.assertEqual(event["remove_edges"], ["O3-H1"])

    def test_patch_cannot_change_identity_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            before = state_path.read_text(encoding="utf-8")

            for label, patch, field in (
                ("edge from", {"update_edges": [{"id": "O2-H1", "set": {"from": "O1"}}]}, "from"),
                ("edge to", {"update_edges": [{"id": "O2-H1", "unset": ["to"]}]}, "to"),
                ("node type", {"update_nodes": [{"id": "H1", "unset": ["type"]}]}, "type"),
            ):
                with self.subTest(label):
                    result = self.record(state_path, {"reason": "r", **patch})
                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertIn(field, result.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_reason_only_record_resyncs_a_hand_edited_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.ok(run_cli("review", str(state_path), "--reviewer", "reviewer-1", "--verdict", "pass", "--findings", "Quotes match."))

            def drop_edge_and_lower_prior(state: dict) -> None:
                state["edges"] = [item for item in state["edges"] if item["id"] != "O1-H2"]
                next(node for node in state["nodes"] if node["id"] == "O2")["prior"] = 0.6

            self.hand_edit(state_path, drop_edge_and_lower_prior)
            self.ok(self.record(state_path, {"reason": "Hand edit: dropped O1-H2, lowered O2's prior"}))

            state = self.load(state_path)
            self.assertEqual(state["events"][-1]["remove_edges"], ["O1-H2"])
            self.assertEqual(next(node for node in state["nodes"] if node["id"] == "O2")["belief"], 0.6)
            stale_review = run_cli("stop", str(state_path), "--reason", "r", "--outcome", "solved")
            self.assertEqual(stale_review.returncode, 1, stale_review.stdout)
            self.assertIn("changed after the latest review", stale_review.stderr)
            self.ok(self.stop_and_audit(state_path))

    def test_record_rejects_a_hand_edited_quote_that_is_not_verbatim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.hand_edit(state_path, lambda state: next(node for node in state["nodes"] if node["id"] == "O1").update({"quote": "The butler left at ten"}))

            result = self.record(state_path, {"reason": "Hand edit: reworded O1"})

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("O1", result.stderr)
            self.assertIn("problem.md", result.stderr)


if __name__ == "__main__":
    unittest.main()
