"""An edge is identified by its ends, written `from-to` (issue #38).

In the final states of the #37 resume loop, 225 of 245 edge ids were exactly `from-to`: the agent
wrote the same thing twice. The id is derived, and two rules keep it unique: one edge per
ordered pair, and no hyphen in a node id."""

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


def edge(source: str, target: str, edge_type: str, **extra: object) -> dict:
    return {"from": source, "to": target, "type": edge_type, **extra}


def observation(node_id: str) -> dict:
    return {"id": node_id, "type": "observation", "text": f"Seen {node_id}", "source": "probe"}


BASE_PATCH = {
    "nodes": [observation("O1"), observation("O2"), {"id": "H1", "type": "hypothesis", "text": "The cause"}],
    "edges": [edge("O1", "H1", "supports"), edge("O2", "H1", "supports", score=4)],
}


class EdgeIdentityTests(unittest.TestCase):
    def ok(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)

    def fails(self, result: subprocess.CompletedProcess[str], *expected: str) -> None:
        self.assertEqual(result.returncode, 1, result.stdout)
        for text in expected:
            self.assertIn(text, result.stderr)

    def start(self, tmp_dir: str) -> Path:
        state_path = Path(tmp_dir) / "state.json"
        self.ok(run_cli("init", "--goal", "Explain the failure", "-o", str(state_path)))
        self.ok(self.record(state_path, BASE_PATCH))
        return state_path

    def record(self, state_path: Path, patch: dict) -> subprocess.CompletedProcess[str]:
        patch_path = state_path.with_name("patch.json")
        patch_path.write_text(json.dumps(patch), encoding="utf-8")
        return run_cli("record", str(state_path), "--patch", str(patch_path))

    def load(self, state_path: Path) -> dict:
        return json.loads(state_path.read_text(encoding="utf-8"))

    def edit(self, state_path: Path, change) -> None:
        state = self.load(state_path)
        change(state)
        state_path.write_text(json.dumps(state), encoding="utf-8")

    def edges(self, state_path: Path) -> dict[tuple[str, str], dict]:
        return {(item["from"], item["to"]): item for item in self.load(state_path)["edges"]}

    def test_edges_are_written_and_stored_without_an_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)

            self.assertEqual(self.load(state_path)["edges"], BASE_PATCH["edges"])
            self.assertIn("- O1 -supports-> H1\n", state_path.with_suffix(".index.md").read_text(encoding="utf-8"))

    def test_edge_carrying_an_id_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            before = state_path.read_text(encoding="utf-8")

            patched = self.record(state_path, {"nodes": [observation("O3")], "edges": [edge("O3", "H1", "supports", id="O3-H1")]})
            self.fails(patched, "edge O3-H1: id was removed", "from-to")
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

            self.edit(state_path, lambda state: state["edges"][0].update({"id": "E1"}))
            self.fails(run_cli("audit", str(state_path)), "edge O1-H1: id was removed")

    def test_updates_removals_and_groups_name_an_edge_by_its_ends(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)

            self.ok(self.record(state_path, {
                "nodes": [observation("O3")],
                "edges": [edge("O3", "H1", "supports")],
                "update_edges": [{"id": "O2-H1", "unset": ["score"]}, {"id": "O1-H1", "set": {"note": "Same probe"}}],
                "factors": [{"id": "F1", "edges": ["O1-H1", "O2-H1"], "score": 4}],
            }))
            edges = self.edges(state_path)
            self.assertNotIn("score", edges[("O2", "H1")])
            self.assertEqual(edges[("O1", "H1")]["note"], "Same probe")
            self.ok(run_cli("audit", str(state_path)))

            self.ok(self.record(state_path, {"remove_edges": ["O3-H1"]}))
            self.assertNotIn(("O3", "H1"), self.edges(state_path))

            self.fails(self.record(state_path, {"remove_edges": ["O3-H1"]}), "remove_edges id O3-H1 does not exist")
            self.fails(self.record(state_path, {"update_edges": [{"id": "O1-H1", "set": {"id": "E1"}}]}), "id")

    def test_one_edge_per_ordered_pair(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)

            self.fails(self.record(state_path, {"edges": [edge("O1", "H1", "contradicts")]}), "edge O1-H1 already exists", "update_edges")
            self.fails(
                self.record(state_path, {"nodes": [observation("O3")], "edges": [edge("O3", "H1", "supports"), edge("O3", "H1", "contradicts")]}),
                "O3-H1",
            )
            # The pair is ordered: the reverse direction is another edge.
            self.ok(self.record(state_path, {"nodes": [{"id": "T1", "type": "test", "text": "Probe again"}], "edges": [edge("H1", "T1", "prompts"), edge("T1", "H1", "prompts")]}))

            self.edit(state_path, lambda state: state["edges"].append(edge("O1", "H1", "contradicts")))
            self.fails(run_cli("audit", str(state_path)), "edge O1-H1 exists more than once", "update_edges")

    def test_node_id_takes_no_hyphen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)

            self.fails(self.record(state_path, {"nodes": [observation("O-3")]}), "node id 'O-3' contains a hyphen", "from-to")

            self.edit(state_path, lambda state: state["nodes"].append(observation("O-3")))
            self.fails(run_cli("audit", str(state_path)), "node id 'O-3' contains a hyphen")


if __name__ == "__main__":
    unittest.main()
