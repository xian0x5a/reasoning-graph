"""The state holds the graph and the claim, and no trace of how it got there (issue #38).

The trace was verified to guard the stop certificate. Its only other reader was one line of the
index, and in the resume loop of #37 it was 16% of the state file. The order of the work is the
order of the lists."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )


def edge(source: str, target: str, edge_type: str, **extra: int) -> dict:
    return {"from": source, "to": target, "type": edge_type, **extra}


def hypothesis(node_id: str) -> dict:
    return {"id": node_id, "type": "hypothesis", "text": f"Claim {node_id}"}


class NoTraceTests(unittest.TestCase):
    def ok(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)

    def fails(self, result: subprocess.CompletedProcess[str], *expected: str) -> None:
        self.assertEqual(result.returncode, 1, result.stdout)
        for text in expected:
            self.assertIn(text, result.stderr)

    def start(self, tmp_dir: str) -> Path:
        state_path = Path(tmp_dir) / "state.json"
        self.ok(run_cli("init", "--goal", "Explain the failure", "-o", str(state_path)))
        self.ok(self.record(state_path, {"nodes": [hypothesis("H1"), hypothesis("H2")], "edges": [edge("H1", "H2", "supports")]}))
        return state_path

    def record(self, state_path: Path, patch: dict) -> subprocess.CompletedProcess[str]:
        patch_path = state_path.with_name("patch.json")
        patch_path.write_text(json.dumps(patch), encoding="utf-8")
        return run_cli("record", str(state_path), "--patch", str(patch_path))

    def load(self, state_path: Path) -> dict:
        return json.loads(state_path.read_text(encoding="utf-8"))

    def test_record_and_refresh_write_no_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.ok(run_cli("refresh", str(state_path)))

            self.assertNotIn("events", self.load(state_path))
            self.assertNotIn("Last record", state_path.with_suffix(".index.md").read_text(encoding="utf-8"))

    def test_state_carrying_events_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            state = self.load(state_path)
            state["events"] = [{"step": 1, "action": "record", "reason": "r", "add_nodes": [], "add_edges": [], "graph_digest": "x"}]
            state_path.write_text(json.dumps(state), encoding="utf-8")

            for rejected in (run_cli("audit", str(state_path)), run_cli("refresh", str(state_path)), self.record(state_path, {"nodes": [hypothesis("H3")]})):
                self.fails(rejected, "events was removed")

    def test_patch_carrying_a_reason_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            before = state_path.read_text(encoding="utf-8")

            self.fails(self.record(state_path, {"reason": "Added a claim", "nodes": [hypothesis("H3")]}), "reason was removed", "note")
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_patch_that_changes_nothing_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)

            self.fails(self.record(state_path, {}), "schema $")

    def test_list_order_is_creation_order(self) -> None:
        # Nothing else records the order of the work, so record appends and never reorders.
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.ok(self.record(state_path, {"nodes": [hypothesis("B9"), hypothesis("A1")], "edges": [edge("B9", "H1", "supports"), edge("A1", "H1", "supports")]}))
            self.ok(self.record(state_path, {
                "remove_nodes": ["H2"],
                "update_nodes": [{"id": "B9", "set": {"score": 4}}],
                "nodes": [hypothesis("H0")],
                "edges": [edge("H0", "A1", "contradicts")],
            }))

            state = self.load(state_path)
            self.assertEqual([node["id"] for node in state["nodes"]], ["G1", "H1", "B9", "A1", "H0"])
            self.assertEqual([(item["from"], item["to"]) for item in state["edges"]], [("B9", "H1"), ("A1", "H1"), ("H0", "A1")])

    def test_refresh_takes_in_a_hand_edit_without_logging_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            state = self.load(state_path)
            state["nodes"].append(hypothesis("H3"))
            state_path.write_text(json.dumps(state), encoding="utf-8")

            refreshed = run_cli("refresh", str(state_path))

            self.ok(refreshed)
            self.assertEqual(refreshed.stdout, "ok\n")
            self.assertNotIn("events", self.load(state_path))
            self.assertIn("H3", state_path.with_suffix(".index.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
