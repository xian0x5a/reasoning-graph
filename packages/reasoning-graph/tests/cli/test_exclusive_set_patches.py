"""Exclusive sets through the CLI: record patches, the index file, and no belief in agent output."""

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
PERCENT = re.compile(r"\d\s*%|<1%")


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )


NODES_PATCH = {
    "nodes": [
        {"id": "O1", "type": "observation", "text": "The log shows the gardener at ten", "source": "greenhouse log"},
        {"id": "H1", "type": "hypothesis", "text": "The gardener did it"},
        {"id": "H2", "type": "hypothesis", "text": "The butler did it"},
        {"id": "H3", "type": "hypothesis", "text": "The cook did it"},
    ],
    "edges": [
        {"from": "O1", "to": "H1", "type": "supports"},
        {"from": "O1", "to": "H2", "type": "supports"},
    ],
}


class ExclusiveSetCliTests(unittest.TestCase):
    def start(self, tmp_dir: str) -> Path:
        state_path = Path(tmp_dir) / "state.json"
        self.assertEqual(run_cli("init", "--goal", "Who did it?", "-o", str(state_path)).returncode, 0)
        self.ok(self.record(state_path, NODES_PATCH))
        return state_path

    def ok(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)

    def record(self, state_path: Path, patch: dict) -> subprocess.CompletedProcess[str]:
        patch_path = state_path.with_name("patch.json")
        patch_path.write_text(json.dumps(patch), encoding="utf-8")
        return run_cli("record", str(state_path), "--patch", str(patch_path))

    def sets(self, state_path: Path) -> list[dict]:
        return json.loads(state_path.read_text(encoding="utf-8")).get("exclusive_sets", [])

    def test_a_patch_adds_replaces_and_removes_sets_by_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)

            self.ok(self.record(state_path, {"exclusive_sets": [
                {"id": "X1", "members": ["H1", "H2"], "note": "one culprit"},
                {"id": "X2", "members": ["H2", "H3"]},
            ]}))
            self.assertEqual([item["id"] for item in self.sets(state_path)], ["X1", "X2"])

            self.ok(self.record(state_path, {"exclusive_sets": [{"id": "X1", "members": ["H1", "H3"]}]}))
            by_id = {item["id"]: item for item in self.sets(state_path)}
            self.assertEqual(by_id["X1"]["members"], ["H1", "H3"])
            self.assertEqual(len(by_id), 2)

            self.ok(self.record(state_path, {"remove_exclusive_sets": ["X1"]}))
            self.assertEqual([item["id"] for item in self.sets(state_path)], ["X2"])

    def test_removing_a_missing_set_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            before = state_path.read_text(encoding="utf-8")

            result = self.record(state_path, {"remove_exclusive_sets": ["X9"]})

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_removing_a_member_node_that_a_set_still_names_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.ok(self.record(state_path, {"exclusive_sets": [{"id": "X1", "members": ["H1", "H2"]}]}))
            before = state_path.read_text(encoding="utf-8")

            result = self.record(state_path, {"remove_nodes": ["H3", "H2"]})

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_invalid_sets_in_a_patch_are_rejected_and_nothing_is_written(self) -> None:
        bad_sets = {
            "one member": {"id": "X1", "members": ["H1"]},
            "duplicate member": {"id": "X1", "members": ["H1", "H1"]},
            "unknown member": {"id": "X1", "members": ["H1", "H9"]},
            "observation member": {"id": "X1", "members": ["H1", "O1"]},
            "goal member": {"id": "X1", "members": ["H1", "G1"]},
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            before = state_path.read_text(encoding="utf-8")
            for name, bad in bad_sets.items():
                with self.subTest(name):
                    self.assertEqual(self.record(state_path, {"exclusive_sets": [bad]}).returncode, 1)
                    self.assertEqual(state_path.read_text(encoding="utf-8"), before)
            with self.subTest("duplicate set ids"):
                twice = [{"id": "X1", "members": ["H1", "H2"]}, {"id": "X1", "members": ["H2", "H3"]}]
                self.assertEqual(self.record(state_path, {"exclusive_sets": twice}).returncode, 1)
                self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_the_index_lists_each_set_with_members_and_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.ok(self.record(state_path, {"exclusive_sets": [{"id": "X1", "members": ["H1", "H2"], "note": "one culprit"}]}))

            index = state_path.with_suffix(".index.md").read_text(encoding="utf-8")

            self.assertIn("## Exclusive sets", index)
            self.assertIn("- X1 [H1, H2] | note: one culprit", index)

    def test_commands_print_no_belief_with_or_without_sets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            results = [
                self.record(state_path, {"exclusive_sets": [{"id": "X1", "members": ["H1", "H2"]}]}),
                run_cli("refresh", str(state_path)),
                run_cli("audit", str(state_path)),
            ]
            for result in results:
                with self.subTest(result.args[-2:]):
                    shown = result.stdout + result.stderr
                    self.assertNotIn("belief", shown)
                    self.assertIsNone(PERCENT.search(shown), shown)


if __name__ == "__main__":
    unittest.main()
