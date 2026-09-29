"""One record patch carries any graph edit.

In the #34 A/B, skill runs averaged 5.5 record calls and 1.5 Python hand-edits of state.json, because a
patch could not change or remove an edge, remove a node or factor, or drop a field (issue #36 comment
5861985148)."""

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


def edge(source: str, target: str, edge_type: str, **extra: int) -> dict:
    return {"id": f"{source}-{target}", "from": source, "to": target, "type": edge_type, "reasoning": "Test edge.", **extra}


def observation(node_id: str, quote: str) -> dict:
    return {"id": node_id, "type": "observation", "text": quote, "source": "problem.md", "quote": quote, "score": 5}


BASE_PATCH = {
    "reason": "Read the story",
    "nodes": [
        observation("O1", "The butler left at nine"),
        observation("O2", "The gardener stayed late, or so he said"),
        {"id": "H1", "type": "hypothesis", "text": "The gardener did it", "score": 3},
        {"id": "H2", "type": "hypothesis", "text": "The butler did it", "score": 2},
        {"id": "CS1", "type": "candidate_solution", "text": "The gardener", "answer_kind": "exact_answer", "score": 5},
    ],
    "edges": [
        edge("O2", "H1", "supports", score=4),
        edge("O1", "H1", "contradicts", score=3),
        edge("O1", "H2", "supports", score=3),
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

    def stop_and_audit(self, state_path: Path) -> subprocess.CompletedProcess[str]:
        self.ok(run_cli("stop", str(state_path), "--reason", "Test ends here", "--outcome", "inconclusive"))
        return run_cli("audit", str(state_path))

    def test_one_patch_updates_unsets_and_removes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)

            self.ok(self.record(state_path, {
                "reason": "Fold the review fixes into one patch",
                "update_nodes": [{"id": "CS1", "unset": ["score"]}, {"id": "H1", "set": {"note": "Only his word"}}],
                "update_edges": [{"id": "O2-H1", "set": {"score": 2}}, {"id": "O1-H1", "unset": ["score"]}],
                "remove_nodes": ["H2"],
            }))

            state = self.load(state_path)
            nodes = {node["id"]: node for node in state["nodes"]}
            edges = {item["id"]: item for item in state["edges"]}
            self.assertNotIn("score", nodes["CS1"])
            self.assertEqual(nodes["H1"]["note"], "Only his word")
            self.assertNotIn("H2", nodes)
            self.assertEqual(edges["O2-H1"]["score"], 2)
            self.assertNotIn("score", edges["O1-H1"])
            # Removing a node takes its edges with it.
            self.assertNotIn("O1-H2", edges)
            event = state["events"][-1]
            self.assertEqual(event["remove_nodes"], ["H2"])
            self.assertEqual(event["remove_edges"], ["O1-H2"])
            self.assertEqual(event["updated_nodes"], [{"id": "CS1", "fields": ["score"]}, {"id": "H1", "fields": ["note"]}])
            self.assertEqual(event["updated_edges"], [{"id": "O2-H1", "fields": ["score"]}, {"id": "O1-H1", "fields": ["score"]}])
            self.ok(run_cli("validate", str(state_path)))

    def test_audit_accepts_an_object_removed_and_added_again(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)

            self.ok(self.record(state_path, {"reason": "Drop the weak link", "remove_edges": ["O1-H2"]}))
            self.ok(self.record(state_path, {"reason": "Restore it", "edges": [edge("O1", "H2", "supports", score=2)]}))

            self.ok(self.stop_and_audit(state_path))

    def test_removing_a_factor_input_needs_the_factor_removed_too(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.ok(self.record(state_path, {
                "reason": "Both clues come from the gardener",
                "nodes": [observation("O3", "or so he said")],
                "edges": [edge("O3", "H1", "supports")],
                "update_edges": [{"id": "O2-H1", "unset": ["score"]}],
                "factors": [{"id": "F1", "edges": ["O2-H1", "O3-H1"], "score": 4, "note": "One witness."}],
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


    def test_record_reports_quote_and_validation_failures_together(self) -> None:
        # A bad quote used to hide validation errors until the next record.
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            before = state_path.read_text(encoding="utf-8")

            result = self.record(state_path, {
                "reason": "r",
                "nodes": [observation("O3", "The butler left at ten")],
                "edges": [edge("O3", "H9", "supports")],
            })

            self.assertEqual(result.returncode, 1, result.stdout)
            for text in ("O3", "problem.md", "H9"):
                self.assertIn(text, result.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
