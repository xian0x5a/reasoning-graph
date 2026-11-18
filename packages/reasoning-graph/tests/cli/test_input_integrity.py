"""Malformed input handling and atomic state writes."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
FIXTURE = PACKAGE_ROOT / "tests" / "fixtures" / "valid" / "minimal-state.json"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )


class MalformedStateInputTests(unittest.TestCase):
    MALFORMED_DOCUMENTS = {
        "list": ("[]", "state must be an object"),
        "null": ("null", "state must be an object"),
        "bad-score": (
            json.dumps({"nodes": [{"id": "A1", "type": "hypothesis", "score": "high"}], "edges": []}),
            "score",
        ),
    }

    def test_audit_reports_structured_error_for_malformed_documents(self) -> None:
        for label, (document, expected) in self.MALFORMED_DOCUMENTS.items():
            with self.subTest(document=label), tempfile.TemporaryDirectory() as tmp_dir:
                state_path = Path(tmp_dir) / "state.json"
                state_path.write_text(document, encoding="utf-8")

                result = run_cli("audit", str(state_path))

                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("error: schema", result.stderr)
                self.assertIn(expected, result.stderr)
                self.assertNotIn("AttributeError", result.stderr)
                self.assertNotIn("has no attribute", result.stderr)

    def test_audit_fails_cleanly_for_non_object_documents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            state_path.write_text("[1, 2]", encoding="utf-8")

            result = run_cli("audit", str(state_path))

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("state must be an object", result.stderr)
            self.assertNotIn("has no attribute", result.stderr)


PYTHON_ERROR_FRAGMENTS = ("has no attribute", "unhashable", "not iterable", "object is not", "does not support", "Traceback")


def state_document(**overrides: object) -> dict:
    document: dict = {
        "nodes": [{"id": "G1", "type": "goal", "text": "Who did it?"}, {"id": "H1", "type": "hypothesis", "text": "The gardener"}],
        "edges": [{"from": "H1", "to": "G1", "type": "answers", "answer_kind": "exact_answer"}],
    }
    document.update(overrides)
    return document


def with_node(node: object) -> dict:
    return state_document(nodes=[node])


def with_edge(**fields: object) -> dict:
    edge = {"from": "H1", "to": "G1", "type": "answers", "answer_kind": "exact_answer"} | fields
    return state_document(edges=[edge])


def with_goal_policy(**policy: object) -> dict:
    return state_document(goal_policy=policy)


# label -> (state document, location the error should name)
WRONG_SHAPE_DOCUMENTS = {
    "non-object-node": ({"nodes": ["oops"], "edges": []}, "$.nodes[0]"),
    "nodes-as-object": ({"nodes": {"a": 1}, "edges": []}, "$.nodes"),
    "edges-null": (state_document(edges=None), "$.edges"),
    "node-id-list": (with_node({"id": ["x"], "type": "goal", "text": "t"}), "$.nodes[0].id"),
    "node-type-list": (with_node({"id": "G1", "type": ["goal"], "text": "t"}), "$.nodes[0].type"),
    "edge-from-list": (with_edge(**{"from": ["H1"]}), "$.edges[0].from"),
    "edge-to-list": (with_edge(to=["G1"]), "$.edges[0].to"),
    "edge-type-list": (with_edge(type=["answers"]), "$.edges[0].type"),
    "accepted-goal-list": (with_goal_policy(accepted_goals=[["G1"]]), "$.goal_policy.accepted_goals[0]"),
    "optional-goal-list": (with_goal_policy(optional_goals=[["G1"]]), "$.goal_policy.optional_goals[0]"),
    "goal-group-goal-list": (state_document(goal_groups=[{"id": "GG1", "goals": [["G1"]]}]), "$.goal_groups[0].goals[0]"),
    "removed-solutions-entry-list": (state_document(solutions=[["S1"]]), "solutions"),
}


class WrongShapeStateTests(unittest.TestCase):
    def assert_clean_validation_error(self, result: subprocess.CompletedProcess[str], location: str) -> None:
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("error:", result.stderr)
        self.assertIn(location, result.stderr)
        for fragment in PYTHON_ERROR_FRAGMENTS:
            self.assertNotIn(fragment, result.stderr)

    def test_audit_and_refresh_report_wrong_shapes_as_validation_errors(self) -> None:
        for label, (document, location) in WRONG_SHAPE_DOCUMENTS.items():
            for command in ("audit", "refresh"):
                with self.subTest(document=label, command=command), tempfile.TemporaryDirectory() as tmp_dir:
                    state_path = Path(tmp_dir) / "state.json"
                    state_path.write_text(json.dumps(document), encoding="utf-8")

                    self.assert_clean_validation_error(run_cli(command, str(state_path)), location)

    def test_record_rejects_wrong_shapes_and_leaves_the_state_file_untouched(self) -> None:
        cases = {
            "edges-null": (json.dumps(state_document(edges=None)), {"answer": ""}),
            "non-object-node": (json.dumps({"nodes": ["oops"], "edges": []}), {"answer": ""}),
            "node-id-list": (json.dumps(with_node({"id": ["x"], "type": "goal", "text": "t"})), {"answer": ""}),
            "top-level-list": ("[]", {"answer": ""}),
            "summary-string": (json.dumps(state_document(summary="text")), {"answer": "H1"}),
        }
        for label, (document, patch) in cases.items():
            with self.subTest(document=label), tempfile.TemporaryDirectory() as tmp_dir:
                state_path = Path(tmp_dir) / "state.json"
                patch_path = Path(tmp_dir) / "patch.json"
                state_path.write_text(document, encoding="utf-8")
                patch_path.write_text(json.dumps(patch), encoding="utf-8")
                before = state_path.read_bytes()

                result = run_cli("record", str(state_path), "--patch", str(patch_path))

                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("error:", result.stderr)
                for fragment in PYTHON_ERROR_FRAGMENTS:
                    self.assertNotIn(fragment, result.stderr)
                self.assertEqual(state_path.read_bytes(), before)

    def test_removed_field_is_still_named_alongside_a_wrong_shape(self) -> None:
        document = {
            "nodes": [{"id": "H1", "type": "hypothesis", "text": "The gardener", "belief": 0.5}],
            "edges": None,
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            state_path.write_text(json.dumps(document), encoding="utf-8")

            result = run_cli("audit", str(state_path))

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("belief was removed", result.stderr)

    def test_patch_repairs_a_hand_edit_with_the_wrong_json_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            patch_path = Path(tmp_dir) / "patch.json"
            state_path.write_text(
                json.dumps({"nodes": [{"id": "H1", "type": "hypothesis", "text": "The gardener", "score": "4"}], "edges": []}),
                encoding="utf-8",
            )
            patch_path.write_text(json.dumps({"update_nodes": [{"id": "H1", "set": {"score": 4}}]}), encoding="utf-8")

            result = run_cli("record", str(state_path), "--patch", str(patch_path))

            self.assertEqual(result.returncode, 0, result.stderr)
            written = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(written["nodes"][0]["score"], 4)
            self.assertIsInstance(written["nodes"][0]["score"], int)


def record_step(state_path: Path, patch_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    patch_path = patch_path or state_path.with_name("patch.json")
    patch_path.write_text(json.dumps({"answer": ""}), encoding="utf-8")
    return run_cli("record", str(state_path), "--patch", str(patch_path))


class AtomicStateWriteTests(unittest.TestCase):
    def test_in_place_write_leaves_no_temporary_files_and_preserves_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            state_path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
            os.chmod(state_path, 0o640)

            result = record_step(state_path)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(sorted(path.name for path in Path(tmp_dir).iterdir()), ["patch.json", "state.html", "state.index.md", "state.json"])
            self.assertEqual(os.stat(state_path).st_mode & 0o777, 0o640)
            json.loads(state_path.read_text(encoding="utf-8"))

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
    def test_failed_write_keeps_original_state_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_dir = Path(tmp_dir) / "locked"
            state_dir.mkdir()
            state_path = state_dir / "state.json"
            original = FIXTURE.read_text(encoding="utf-8")
            state_path.write_text(original, encoding="utf-8")
            os.chmod(state_dir, 0o500)
            try:
                result = record_step(state_path, Path(tmp_dir) / "patch.json")
            finally:
                os.chmod(state_dir, 0o700)

            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original)
            self.assertEqual([path.name for path in state_dir.iterdir()], ["state.json"])


if __name__ == "__main__":
    unittest.main()
