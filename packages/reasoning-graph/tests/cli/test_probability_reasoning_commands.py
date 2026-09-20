import json
import subprocess
import sys

import pytest

from reasoning_graph.cli import starter_state


@pytest.mark.parametrize("command", ["seed", "expand"])
@pytest.mark.parametrize("invalid_part", ["score", "reasoning", "long_reasoning", "update_score"])
def test_invalid_patch_does_not_modify_state(tmp_path, command, invalid_part):
    state = starter_state("default")
    state["frontier"] = [{"id": "Q1", "node": "G1"}]
    state_path = tmp_path / "state.json"
    patch_path = tmp_path / "patch.json"
    state_path.write_text(json.dumps(state))

    def run(*args):
        return subprocess.run([sys.executable, "-c", "from reasoning_graph.cli import main; raise SystemExit(main())", *args], capture_output=True, text=True)

    if command == "expand":
        assert run("next", str(state_path), "--pop").returncode == 0
    original = state_path.read_bytes()
    patch = {
        "nodes": [{"id": "D1", "type": "derived", "confidence": 0.9}],
        "edges": [{"id": "G1-D1", "from": "G1", "to": "D1", "type": "prompts",
                   "reasoning": "The objective motivates checking this conclusion."}],
        "frontier": [{"id": "Q2", "node": "D1"}],
    }
    if invalid_part == "score":
        del patch["nodes"][0]["confidence"]
    elif invalid_part == "reasoning":
        del patch["edges"][0]["reasoning"]
    elif invalid_part == "long_reasoning":
        patch["edges"][0]["reasoning"] = "Sentence. " * 6
    else:
        patch["update_nodes"] = [{"id": "G1", "set": {"probability": None}}]
    patch_path.write_text(json.dumps(patch))
    args = [command, str(state_path), "--patch", str(patch_path)]
    if command == "expand":
        args += ["--item", "Q1"]
    result = run(*args)
    assert result.returncode != 0
    assert ("probability" if invalid_part == "update_score" else "schema") in result.stderr
    assert state_path.read_bytes() == original

