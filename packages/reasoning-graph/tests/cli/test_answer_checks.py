"""Checks on a claimed answer, learned from the Spooky Manor run: unanswered goals (#29),
answer-to-candidate matching (#30), and strict test results (#31). `audit` runs them once
`summary.answer` is set (issue #38)."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
FIXTURE = PACKAGE_ROOT / "tests" / "fixtures" / "valid" / "reasoning-graph-strict-good.json"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )


def write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


ROOM_SEED = {
    "nodes": [
        {"id": "E1", "type": "observation", "text": "Room 1 shows eight windows with tinted panes", "source": "room page"},
        {"id": "A1", "type": "hypothesis", "text": "The panes are Braille cells", "score": 3},
        {"id": "T1", "type": "test", "text": "Decode the panes as Braille and probe the URL"},
    ],
    "edges": [
        {"from": "E1", "to": "A1", "type": "supports", "score": 3},
        {"from": "A1", "to": "T1", "type": "prompts"},
    ],
}

ROOM_ONE_SOLVED = {
    "nodes": [
        {"id": "E2", "type": "observation", "text": "Braille decode reads TWOSIGNS and the URL returns 200", "source": "probe", "score": 5},
        {"id": "CS1", "type": "candidate_solution", "text": "TwoSigns", "answer_kind": "exact_answer"},
        {"id": "G2", "type": "goal", "text": "Find the next URL path under /TwoSigns/"},
        {"id": "E3", "type": "observation", "text": "Room 2 shows a waveform image", "source": "room page"},
        {"id": "A2", "type": "hypothesis", "text": "The waveform encodes 5-bit characters", "score": 3},
        {"id": "T2", "type": "test", "text": "Decode the waveform and probe the URL"},
    ],
    "edges": [
        {"from": "T1", "to": "E2", "type": "leads_to"},
        {"from": "E2", "to": "CS1", "type": "leads_to"},
        {"from": "CS1", "to": "G1", "type": "answers"},
        {"from": "G1", "to": "G2", "type": "requires"},
        {"from": "E3", "to": "A2", "type": "supports", "score": 2},
        {"from": "A2", "to": "T2", "type": "prompts"},
    ],
    "answer": "TwoSigns",
}


class SpookyManorFlow(unittest.TestCase):
    """Drive a two-room trail up to the room 2 decode, with room 1 claimed as the answer."""

    def start_trail(self, tmp_dir: str) -> Path:
        state_path = Path(tmp_dir) / "state.json"
        self.assertEqual(run_cli("init", "--goal", "Find the URL path into the manor", "-o", str(state_path)).returncode, 0)
        self.ok(self.record(tmp_dir, state_path, "room1", ROOM_SEED))
        self.ok(self.record(tmp_dir, state_path, "room2", ROOM_ONE_SOLVED))
        return state_path

    def ok(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)

    def record(self, tmp_dir: str, state_path: Path, name: str, patch: dict) -> subprocess.CompletedProcess[str]:
        return run_cli("record", str(state_path), "--patch", str(write_json(Path(tmp_dir) / f"{name}.json", patch)))


class UnansweredGoalTests(SpookyManorFlow):
    PROFILE_ONLY = {
        "nodes": [{"id": "E4", "type": "observation", "text": "Spectral profile shows 20 tracks", "source": "fft"}],
        "edges": [{"from": "T2", "to": "E4", "type": "leads_to"}],
    }

    def test_answer_fails_while_an_accepted_goal_is_unanswered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start_trail(tmp_dir)
            self.ok(self.record(tmp_dir, state_path, "profile", self.PROFILE_ONLY))

            audit = run_cli("audit", str(state_path))

            self.assertEqual(audit.returncode, 1, audit.stdout)
            self.assertIn("accepted goal G2", audit.stderr)
            self.assertIn("unanswered", audit.stderr)

            self.ok(self.record(tmp_dir, state_path, "withdraw", {"answer": ""}))
            self.ok(run_cli("audit", str(state_path)))

    def test_parent_goal_is_not_answered_until_required_sub_goal_is(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start_trail(tmp_dir)
            self.ok(self.record(tmp_dir, state_path, "profile", self.PROFILE_ONLY))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["goal_policy"] = {"accepted_goals": ["G1"]}
            write_json(state_path, state)

            audit = run_cli("audit", str(state_path))

            self.assertEqual(audit.returncode, 1, audit.stdout)
            self.assertIn("accepted goal G1", audit.stderr)
            self.assertIn("requires unanswered goal G2", audit.stderr)

    def test_optional_goal_does_not_block_the_answer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start_trail(tmp_dir)
            self.ok(self.record(tmp_dir, state_path, "profile", self.PROFILE_ONLY))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["goal_policy"] = {"optional_goals": ["G2"]}
            write_json(state_path, state)

            self.ok(run_cli("audit", str(state_path)))

    def test_goal_to_goal_edges_must_be_requires(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state = json.loads(FIXTURE.read_text(encoding="utf-8"))
            state["nodes"].append({"id": "G2", "type": "goal", "text": "Sub goal"})
            state["edges"].append({"from": "G1", "to": "G2", "type": "leads_to"})
            result = run_cli("audit", str(write_json(Path(tmp_dir) / "state.json", state)))

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("goal -> goal must use requires", result.stderr)


class AnswerMatchesCandidateTests(unittest.TestCase):
    def fixture_state(self) -> dict:
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_report_answer_names_the_candidate_the_claim_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state = self.fixture_state()
            state["report"] = {"answer": "The trail ends at Photophone."}

            result = run_cli("audit", str(write_json(Path(tmp_dir) / "state.json", state)))

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("report.answer does not name candidate CS1", result.stderr)
            self.assertIn("The trail ends at Photophone.", result.stderr)

        with tempfile.TemporaryDirectory() as tmp_dir:
            state = self.fixture_state()
            state["summary"] = {"answer": "Candidate from A1 wins."}
            state["report"] = {"answer": "CS1 wins."}
            result = run_cli("audit", str(write_json(Path(tmp_dir) / "state.json", state)))
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_draft_must_name_the_answer_candidate_among_several(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state = self.fixture_state()
            state["nodes"].append({"id": "CS2", "type": "candidate_solution", "text": "Stale alternative", "answer_kind": "exact_answer", "score": 1})
            state["edges"].append({"from": "CS2", "to": "G1", "type": "answers"})
            state_path = write_json(Path(tmp_dir) / "state.json", state)
            draft_path = Path(tmp_dir) / "answer.md"
            draft_path.write_text("Final answer: Stale alternative.", encoding="utf-8")

            rejected = run_cli("audit", str(state_path), "--draft", str(draft_path))

            self.assertEqual(rejected.returncode, 1, rejected.stdout)
            self.assertIn("draft does not mention candidate CS1", rejected.stderr)

            draft_path.write_text("Final answer: Candidate from A1.", encoding="utf-8")
            self.assertEqual(run_cli("audit", str(state_path), "--draft", str(draft_path)).returncode, 0)

    def test_report_rows_and_winning_path_must_resolve_to_graph_nodes(self) -> None:
        cases = {
            "unknown-candidate-row": ({"candidates": [{"id": "CS9", "name": "Ghost"}]}, "report.candidates[0].id references missing candidate_solution 'CS9'"),
            "non-candidate-row": ({"candidates": [{"id": "A1", "name": "Route"}]}, "report.candidates[0].id references missing candidate_solution 'A1'"),
            "unknown-path-node": ({"candidates": [{"id": "CS1", "path_nodes": ["A1", "X9"]}]}, "report.candidates[0].path_nodes[1] references missing node 'X9'"),
            "unmatched-winning-path": ({"winning_path": ["Likely cause", "Photophone"]}, "report.winning_path[1] 'Photophone' matches no node id or exact node text"),
        }
        for label, (report, expected) in cases.items():
            with self.subTest(case=label), tempfile.TemporaryDirectory() as tmp_dir:
                state = self.fixture_state()
                state["report"] = report
                result = run_cli("audit", str(write_json(Path(tmp_dir) / "state.json", state)))
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(expected, result.stderr)


class StrictTestResultTests(SpookyManorFlow):
    def test_answer_fails_on_a_hypothesis_as_a_test_result(self) -> None:
        # A conclusion drawn from a probe is not what was seen; the observation must be recorded first.
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start_trail(tmp_dir)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["goal_policy"] = {"optional_goals": ["G2"]}
            write_json(state_path, state)
            self.ok(self.record(tmp_dir, state_path, "conclusion", {
                "nodes": [{"id": "H1", "type": "hypothesis", "text": "The tracks are not ITA2", "score": 5}],
                "edges": [
                    {"from": "T2", "to": "H1", "type": "leads_to"},
                    {"from": "H1", "to": "A2", "type": "contradicts", "score": 4},
                ],
            }))

            audit = run_cli("audit", str(state_path))

            self.assertEqual(audit.returncode, 1, audit.stdout)
            self.assertIn("without a recorded result observation: T2", audit.stderr)


class GroundedPathTests(unittest.TestCase):
    """A claimed answer needs a candidate that rests on observations,
    not on hand-set scores on the claims under it."""

    def ok(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)

    def recorded_state(self, tmp_dir: str, nodes: list[dict], edges: list[dict], candidate_score: int | None = None) -> Path:
        state_path = Path(tmp_dir) / "state.json"
        self.ok(run_cli("init", "--goal", "Explain the failure", "-o", str(state_path)))
        patch = {
            "answer": "CS1",
            "nodes": [
                {"id": "T1", "type": "test", "text": "Probe the system"},
                {"id": "O1", "type": "observation", "text": "Probe output", "source": "probe", "score": 5},
                {"id": "CS1", "type": "candidate_solution", "text": "Root cause", "answer_kind": "exact_answer"}
                | ({"score": candidate_score} if candidate_score is not None else {}),
                *nodes,
            ],
            "edges": [
                {"from": "T1", "to": "O1", "type": "leads_to"},
                {"from": "CS1", "to": "G1", "type": "answers"},
                *edges,
            ],
        }
        self.ok(run_cli("record", str(state_path), "--patch", str(write_json(Path(tmp_dir) / "record.json", patch))))
        return state_path

    def audit(self, state_path: Path) -> subprocess.CompletedProcess[str]:
        return run_cli("audit", str(state_path))

    @staticmethod
    def hypothesis(node_id: str, score: int | None = None) -> dict:
        node = {"id": node_id, "type": "hypothesis", "text": f"Claim {node_id}"}
        if score is not None:
            node["score"] = score
        return node

    @staticmethod
    def edge(source: str, target: str, edge_type: str, **extra: int) -> dict:
        return {"from": source, "to": target, "type": edge_type, **extra}

    def test_score_only_hypothesis_fails_the_answer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.recorded_state(tmp_dir, [self.hypothesis("H1", 5)], [self.edge("H1", "CS1", "leads_to")])

            audit = self.audit(state_path)
            self.assertEqual(audit.returncode, 1, audit.stdout)
            self.assertIn("H1", audit.stderr)
            self.assertIn("grounded", audit.stderr)

    def test_score_only_path_passes_once_the_claim_is_withdrawn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.recorded_state(tmp_dir, [self.hypothesis("H1", 5)], [self.edge("H1", "CS1", "leads_to")])
            patch_path = write_json(Path(tmp_dir) / "withdraw.json", {"answer": ""})
            self.ok(run_cli("record", str(state_path), "--patch", str(patch_path)))

            self.ok(self.audit(state_path))

    def test_score_only_candidate_fails_the_answer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.recorded_state(tmp_dir, [], [], candidate_score=5)

            audit = self.audit(state_path)
            self.assertEqual(audit.returncode, 1, audit.stdout)
            self.assertIn("CS1", audit.stderr)

    def test_contradiction_alone_does_not_ground_a_hypothesis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.recorded_state(
                tmp_dir,
                [self.hypothesis("H1", 5)],
                [self.edge("O1", "H1", "contradicts", score=1), self.edge("H1", "CS1", "leads_to")],
            )
            audit = self.audit(state_path)
            self.assertEqual(audit.returncode, 1, audit.stdout)
            self.assertIn("H1", audit.stderr)

    def test_net_supporting_evidence_grounds_a_hypothesis_despite_a_contradiction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.recorded_state(
                tmp_dir,
                [self.hypothesis("H1", 3), {"id": "O2", "type": "observation", "text": "Odd log line", "source": "logs", "score": 5}],
                [
                    self.edge("O1", "H1", "supports", score=5),
                    self.edge("O2", "H1", "contradicts", score=1),
                    self.edge("H1", "CS1", "leads_to"),
                ],
            )
            self.ok(self.audit(state_path))

    def test_elimination_recorded_as_support_grounds_the_survivor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.recorded_state(
                tmp_dir,
                [self.hypothesis("H1", 3), self.hypothesis("H2", 3)],
                [
                    self.edge("O1", "H2", "contradicts", score=5),
                    self.edge("O1", "H1", "supports", score=5),
                    self.edge("H1", "CS1", "leads_to"),
                ],
            )
            self.ok(self.audit(state_path))

    def test_premise_chain_is_grounded_only_when_every_premise_is(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            grounded = self.recorded_state(tmp_dir, [self.hypothesis("H1")], [self.edge("O1", "H1", "leads_to"), self.edge("H1", "CS1", "leads_to")])
            self.ok(self.audit(grounded))

        with tempfile.TemporaryDirectory() as tmp_dir:
            mixed = self.recorded_state(
                tmp_dir,
                [self.hypothesis("H0", 5), self.hypothesis("H1")],
                [self.edge("O1", "H1", "leads_to"), self.edge("H0", "H1", "leads_to"), self.edge("H1", "CS1", "leads_to")],
            )
            audit = self.audit(mixed)
            self.assertEqual(audit.returncode, 1, audit.stdout)
            self.assertIn("H0", audit.stderr)

    def test_support_from_an_ungrounded_hypothesis_does_not_ground_its_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.recorded_state(
                tmp_dir,
                [self.hypothesis("H1", 3), self.hypothesis("H2", 5)],
                [self.edge("H2", "H1", "supports", score=5), self.edge("H1", "CS1", "leads_to")],
            )
            audit = self.audit(state_path)
            self.assertEqual(audit.returncode, 1, audit.stdout)
            self.assertIn("H1", audit.stderr)

    def test_support_from_a_grounded_hypothesis_grounds_its_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.recorded_state(
                tmp_dir,
                [self.hypothesis("H1", 3), self.hypothesis("H2")],
                [self.edge("O1", "H2", "leads_to"), self.edge("H2", "H1", "supports", score=5), self.edge("H1", "CS1", "leads_to")],
            )
            self.ok(self.audit(state_path))

    def test_contradiction_from_an_ungrounded_source_still_weighs_against_grounding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.recorded_state(
                tmp_dir,
                [self.hypothesis("H1", 5), self.hypothesis("H2", 3)],
                [
                    self.edge("O1", "H1", "supports", score=3),
                    self.edge("H2", "H1", "contradicts", score=5),
                    self.edge("H1", "CS1", "leads_to"),
                ],
            )
            audit = self.audit(state_path)
            self.assertEqual(audit.returncode, 1, audit.stdout)
            self.assertIn("H1", audit.stderr)


if __name__ == "__main__":
    unittest.main()
