"""Stop gates learned from the Spooky Manor run: unanswered goals (#29), answer-to-candidate
matching (#30), and strict test results (#31)."""

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
        {"id": "E1", "type": "observation", "text": "Room 1 shows eight windows with tinted panes", "source": "room page", "prior": 1.0},
        {"id": "A1", "type": "hypothesis", "text": "The panes are Braille cells", "prior": 0.6},
        {"id": "T1", "type": "test", "text": "Decode the panes as Braille and probe the URL"},
    ],
    "edges": [
        {"id": "E1-A1", "from": "E1", "to": "A1", "type": "supports", "likelihood_ratio": 2, "reasoning": "Two-by-three panes match Braille cells."},
        {"id": "A1-T1", "from": "A1", "to": "T1", "type": "prompts", "reasoning": "The Braille reading motivates a decode probe."},
    ],
    "reason": "Read room 1",
}

ROOM_ONE_SOLVED = {
    "nodes": [
        {"id": "E2", "type": "observation", "text": "Braille decode reads TWOSIGNS and the URL returns 200", "source": "probe", "prior": 0.95},
        {"id": "CS1", "type": "candidate_solution", "text": "TwoSigns", "answer_kind": "exact_answer"},
        {"id": "G2", "type": "goal", "text": "Find the next URL path under /TwoSigns/"},
        {"id": "E3", "type": "observation", "text": "Room 2 shows a waveform image", "source": "room page", "prior": 1.0},
        {"id": "A2", "type": "hypothesis", "text": "The waveform encodes 5-bit characters", "prior": 0.5},
        {"id": "T2", "type": "test", "text": "Decode the waveform and probe the URL"},
    ],
    "edges": [
        {"id": "T1-E2", "from": "T1", "to": "E2", "type": "leads_to", "reasoning": "The probe produced this observation."},
        {"id": "E2-CS1", "from": "E2", "to": "CS1", "type": "leads_to", "reasoning": "The confirmed URL is the answer."},
        {"id": "CS1-G1", "from": "CS1", "to": "G1", "type": "answers", "reasoning": "TwoSigns is the room 1 path."},
        {"id": "G1-G2", "from": "G1", "to": "G2", "type": "requires", "reasoning": "The trail continues into room 2."},
        {"id": "E3-A2", "from": "E3", "to": "A2", "type": "supports", "likelihood_ratio": 1.5, "reasoning": "Square waves suggest bit tracks."},
        {"id": "A2-T2", "from": "A2", "to": "T2", "type": "prompts", "reasoning": "The 5-bit reading motivates a decode probe."},
    ],
    "reason": "Solved room 1 and read room 2",
}


class SpookyManorFlow(unittest.TestCase):
    """Drive a strict two-room trail up to the room 2 decode."""

    def start_trail(self, tmp_dir: str) -> Path:
        state_path = Path(tmp_dir) / "state.json"
        self.assertEqual(run_cli("init", "--goal", "Find the URL path into the manor", "--strict", "-o", str(state_path)).returncode, 0)
        self.ok(self.record(tmp_dir, state_path, "room1", ROOM_SEED))
        self.ok(self.record(tmp_dir, state_path, "room2", ROOM_ONE_SOLVED))
        return state_path

    def ok(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)

    def record(self, tmp_dir: str, state_path: Path, name: str, patch: dict) -> subprocess.CompletedProcess[str]:
        return run_cli("record", str(state_path), "--patch", str(write_json(Path(tmp_dir) / f"{name}.json", patch)))


class UnansweredGoalTests(SpookyManorFlow):
    PROFILE_ONLY = {
        "nodes": [{"id": "E4", "type": "observation", "text": "Spectral profile shows 20 tracks", "source": "fft", "prior": 1.0}],
        "edges": [{"id": "T2-E4", "from": "T2", "to": "E4", "type": "leads_to", "reasoning": "The probe produced this profile."}],
        "reason": "Profiled the room 2 waveform",
    }

    def test_solved_stop_is_rejected_while_an_accepted_goal_is_unanswered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start_trail(tmp_dir)
            self.ok(self.record(tmp_dir, state_path, "profile", self.PROFILE_ONLY))
            before = state_path.read_text(encoding="utf-8")

            stopped = run_cli("stop", str(state_path), "--reason", "all rooms solved", "--outcome", "solved")

            self.assertEqual(stopped.returncode, 1, stopped.stdout)
            self.assertIn("accepted goal G2", stopped.stderr)
            self.assertIn("unanswered", stopped.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

            inconclusive = run_cli("stop", str(state_path), "--reason", "room 2 decode unfinished", "--outcome", "inconclusive", "-o", str(Path(tmp_dir) / "stopped.json"))
            self.ok(inconclusive)

    def test_parent_goal_is_not_answered_until_required_sub_goal_is(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start_trail(tmp_dir)
            self.ok(self.record(tmp_dir, state_path, "profile", self.PROFILE_ONLY))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["goal_policy"] = {"accepted_goals": ["G1"]}
            write_json(state_path, state)

            stopped = run_cli("stop", str(state_path), "--reason", "G1 answered", "--outcome", "solved")

            self.assertEqual(stopped.returncode, 1, stopped.stdout)
            self.assertIn("accepted goal G1", stopped.stderr)
            self.assertIn("requires unanswered goal G2", stopped.stderr)

    def test_optional_goal_does_not_block_solved_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start_trail(tmp_dir)
            self.ok(self.record(tmp_dir, state_path, "profile", self.PROFILE_ONLY))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["goal_policy"] = {"optional_goals": ["G2"]}
            write_json(state_path, state)

            self.ok(run_cli("review", str(state_path), "--reviewer", "reviewer-1", "--verdict", "pass", "--findings", "Graph checked."))
            stopped = run_cli("stop", str(state_path), "--reason", "G1 answered; G2 optional", "--outcome", "solved", "-o", str(Path(tmp_dir) / "stopped.json"))

            self.ok(stopped)

    def test_stop_review_and_audit_name_the_unanswered_goal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start_trail(tmp_dir)
            self.ok(self.record(tmp_dir, state_path, "profile", self.PROFILE_ONLY))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            # Forge the terminal events by hand to bypass the CLI preflight.
            step = state["events"][-1]["step"]
            state["events"].extend([
                {"step": step + 1, "action": "rank", "best": "CS1", "belief": 0.95, "candidates": [{"node": "CS1", "belief": 0.95, "effective_truth_cost": 0.051293}]},
                {"step": step + 2, "action": "stop", "reason": "systematically solved stage by stage", "outcome": "solved"},
            ])
            write_json(state_path, state)

            audit = run_cli("audit", str(state_path))
            review = run_cli("stop-review", str(state_path))

            self.assertEqual(audit.returncode, 1, audit.stdout)
            self.assertIn("accepted goal G2", audit.stderr)
            self.assertEqual(review.returncode, 1, review.stderr)
            self.assertIn("verdict: fail", review.stdout)
            self.assertIn("accepted goal G2", review.stdout)

    def test_goal_to_goal_edges_must_be_requires(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state = json.loads(FIXTURE.read_text(encoding="utf-8"))
            state["nodes"].append({"id": "G2", "type": "goal", "text": "Sub goal"})
            state["edges"].append({"id": "G1-G2", "from": "G1", "to": "G2", "type": "leads_to", "reasoning": "wrong relation"})
            result = run_cli("validate", str(write_json(Path(tmp_dir) / "state.json", state)))

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("goal -> goal must use requires", result.stderr)


class AnswerMatchesCandidateTests(unittest.TestCase):
    def stopped_state(self) -> dict:
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def review(self, tmp_dir: str, state: dict, *extra: str) -> subprocess.CompletedProcess[str]:
        return run_cli("stop-review", str(write_json(Path(tmp_dir) / "state.json", state)), *extra)

    def test_answer_fields_must_name_the_best_candidate_for_each_accepted_goal(self) -> None:
        for field in ("summary", "report"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp_dir:
                state = self.stopped_state()
                state[field] = {**state.get(field, {}), "answer": "The trail ends at Photophone."}

                result = self.review(tmp_dir, state)

                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn("verdict: fail", result.stdout)
                self.assertIn(f"{field}.answer does not name best candidate CS1", result.stdout)
                self.assertIn("The trail ends at Photophone.", result.stdout)

        with tempfile.TemporaryDirectory() as tmp_dir:
            state = self.stopped_state()
            state["summary"] = {"answer": "Candidate from A1 wins."}
            state["report"] = {"answer": "CS1 wins."}
            result = self.review(tmp_dir, state)
            self.assertEqual(result.returncode, 0, result.stdout)

    def test_draft_must_name_the_best_candidate_for_the_resolved_goal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state = self.stopped_state()
            state["nodes"].append({"id": "CS2", "type": "candidate_solution", "text": "Stale alternative", "answer_kind": "exact_answer", "prior": 0.1})
            state["edges"].append({"id": "CS2-G1", "from": "CS2", "to": "G1", "type": "answers", "reasoning": "A weaker answer to the same goal."})
            draft_path = Path(tmp_dir) / "answer.md"
            draft_path.write_text("Final answer: Stale alternative.", encoding="utf-8")

            result = self.review(tmp_dir, state, "--draft", str(draft_path))

            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("draft does not mention best candidate CS1", result.stdout)

    def test_report_rows_and_winning_path_must_resolve_to_graph_nodes(self) -> None:
        cases = {
            "unknown-candidate-row": ({"candidates": [{"id": "CS9", "name": "Ghost"}]}, "report.candidates[0].id references missing candidate_solution 'CS9'"),
            "non-candidate-row": ({"candidates": [{"id": "A1", "name": "Route"}]}, "report.candidates[0].id references missing candidate_solution 'A1'"),
            "unknown-path-node": ({"candidates": [{"id": "CS1", "path_nodes": ["A1", "X9"]}]}, "report.candidates[0].path_nodes[1] references missing node 'X9'"),
            "unmatched-winning-path": ({"winning_path": ["Likely cause", "Photophone"]}, "report.winning_path[1] 'Photophone' matches no node id or exact node text"),
        }
        for label, (report, expected) in cases.items():
            with self.subTest(case=label), tempfile.TemporaryDirectory() as tmp_dir:
                state = self.stopped_state()
                state["report"] = report
                result = run_cli("validate", str(write_json(Path(tmp_dir) / "state.json", state)))
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(expected, result.stderr)


class StrictTestResultTests(SpookyManorFlow):
    def test_solved_stop_rejects_a_hypothesis_as_a_test_result(self) -> None:
        # A conclusion drawn from a probe is not what was seen; the observation must be recorded first.
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start_trail(tmp_dir)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["goal_policy"] = {"optional_goals": ["G2"]}
            write_json(state_path, state)
            self.ok(self.record(tmp_dir, state_path, "conclusion", {
                "reason": "Concluded from the decode attempt",
                "nodes": [{"id": "H1", "type": "hypothesis", "text": "The tracks are not ITA2", "prior": 0.9}],
                "edges": [
                    {"id": "T2-H1", "from": "T2", "to": "H1", "type": "leads_to", "reasoning": "The probe suggests this conclusion."},
                    {"id": "H1-A2", "from": "H1", "to": "A2", "type": "contradicts", "likelihood_ratio": 0.3, "reasoning": "Not ITA2 undercuts the 5-bit reading."},
                ],
            }))
            self.ok(run_cli("review", str(state_path), "--reviewer", "reviewer-1", "--verdict", "pass", "--findings", "Graph checked."))

            stopped = run_cli("stop", str(state_path), "--reason", "G1 answered", "--outcome", "solved")

            self.assertEqual(stopped.returncode, 1, stopped.stdout)
            self.assertIn("without a recorded result observation: T2", stopped.stderr)


if __name__ == "__main__":
    unittest.main()


class GroundedPathTests(unittest.TestCase):
    """High-confidence stops need a candidate whose belief is earned from observations,
    not carried by hand-set priors on the claims it rests on."""

    def ok(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)

    def recorded_state(self, tmp_dir: str, nodes: list[dict], edges: list[dict], candidate_prior: float | None = None) -> Path:
        state_path = Path(tmp_dir) / "state.json"
        self.ok(run_cli("init", "--goal", "Explain the failure", "--strict", "-o", str(state_path)))
        patch = {
            "reason": "Probed the system",
            "nodes": [
                {"id": "T1", "type": "test", "text": "Probe the system"},
                {"id": "O1", "type": "observation", "text": "Probe output", "source": "probe", "prior": 0.95},
                {"id": "CS1", "type": "candidate_solution", "text": "Root cause", "answer_kind": "exact_answer"}
                | ({"prior": candidate_prior} if candidate_prior is not None else {}),
                *nodes,
            ],
            "edges": [
                {"id": "T1-O1", "from": "T1", "to": "O1", "type": "leads_to", "reasoning": "The probe produced this output."},
                {"id": "CS1-G1", "from": "CS1", "to": "G1", "type": "answers", "reasoning": "The candidate explains the failure."},
                *edges,
            ],
        }
        self.ok(run_cli("record", str(state_path), "--patch", str(write_json(Path(tmp_dir) / "record.json", patch))))
        return state_path

    def stop(self, state_path: Path, outcome: str = "candidate_threshold_met") -> subprocess.CompletedProcess[str]:
        # The strict profile also requires a review; pass it so these tests isolate grounding.
        self.ok(run_cli("review", str(state_path), "--reviewer", "reviewer-1", "--verdict", "pass", "--findings", "Graph checked."))
        return run_cli("stop", str(state_path), "--reason", "CS1 crosses the belief threshold", "--outcome", outcome, "-o", str(state_path.with_name("stopped.json")))

    @staticmethod
    def hypothesis(node_id: str, prior: float | None = None) -> dict:
        node = {"id": node_id, "type": "hypothesis", "text": f"Claim {node_id}"}
        if prior is not None:
            node["prior"] = prior
        return node

    @staticmethod
    def edge(source: str, target: str, edge_type: str, **extra: float) -> dict:
        return {"id": f"{source}-{target}", "from": source, "to": target, "type": edge_type, "reasoning": "Test edge.", **extra}

    def test_prior_only_hypothesis_blocks_threshold_and_solved_stops(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.recorded_state(tmp_dir, [self.hypothesis("H1", 0.95)], [self.edge("H1", "CS1", "leads_to")])

            for outcome in ("candidate_threshold_met", "solved"):
                stopped = self.stop(state_path, outcome)
                self.assertEqual(stopped.returncode, 1, stopped.stdout)
                self.assertIn("H1", stopped.stderr)
                self.assertIn("grounded", stopped.stderr)

    def test_prior_only_path_may_stop_as_budget_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.recorded_state(tmp_dir, [self.hypothesis("H1", 0.95)], [self.edge("H1", "CS1", "leads_to")])
            self.ok(self.stop(state_path, "budget_exhausted"))

    def test_prior_only_candidate_blocks_threshold_stop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.recorded_state(tmp_dir, [], [], candidate_prior=0.9)

            stopped = self.stop(state_path)
            self.assertEqual(stopped.returncode, 1, stopped.stdout)
            self.assertIn("CS1", stopped.stderr)

    def test_contradiction_alone_does_not_ground_a_hypothesis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.recorded_state(
                tmp_dir,
                [self.hypothesis("H1", 0.99)],
                [self.edge("O1", "H1", "contradicts", likelihood_ratio=0.8), self.edge("H1", "CS1", "leads_to")],
            )
            stopped = self.stop(state_path)
            self.assertEqual(stopped.returncode, 1, stopped.stdout)
            self.assertIn("H1", stopped.stderr)

    def test_net_supporting_evidence_grounds_a_hypothesis_despite_a_contradiction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.recorded_state(
                tmp_dir,
                [self.hypothesis("H1", 0.6), {"id": "O2", "type": "observation", "text": "Odd log line", "source": "logs", "prior": 0.9}],
                [
                    self.edge("O1", "H1", "supports", likelihood_ratio=6),
                    self.edge("O2", "H1", "contradicts", likelihood_ratio=0.8),
                    self.edge("H1", "CS1", "leads_to"),
                ],
            )
            self.ok(self.stop(state_path))

    def test_elimination_recorded_as_support_grounds_the_survivor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.recorded_state(
                tmp_dir,
                [self.hypothesis("H1", 0.5), self.hypothesis("H2", 0.5)],
                [
                    self.edge("O1", "H2", "contradicts", likelihood_ratio=0.1),
                    self.edge("O1", "H1", "supports", likelihood_ratio=9),
                    self.edge("H1", "CS1", "leads_to"),
                ],
            )
            self.ok(self.stop(state_path))

    def test_premise_chain_is_grounded_only_when_every_premise_is(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            grounded = self.recorded_state(tmp_dir, [self.hypothesis("H1")], [self.edge("O1", "H1", "leads_to"), self.edge("H1", "CS1", "leads_to")])
            self.ok(self.stop(grounded))

        with tempfile.TemporaryDirectory() as tmp_dir:
            mixed = self.recorded_state(
                tmp_dir,
                [self.hypothesis("H0", 0.99), self.hypothesis("H1")],
                [self.edge("O1", "H1", "leads_to"), self.edge("H0", "H1", "leads_to"), self.edge("H1", "CS1", "leads_to")],
            )
            stopped = self.stop(mixed)
            self.assertEqual(stopped.returncode, 1, stopped.stdout)
            self.assertIn("H0", stopped.stderr)

    def test_support_from_an_ungrounded_hypothesis_does_not_ground_its_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.recorded_state(
                tmp_dir,
                [self.hypothesis("H1", 0.5), self.hypothesis("H2", 0.9)],
                [self.edge("H2", "H1", "supports", likelihood_ratio=9), self.edge("H1", "CS1", "leads_to")],
            )
            stopped = self.stop(state_path)
            self.assertEqual(stopped.returncode, 1, stopped.stdout)
            self.assertIn("H1", stopped.stderr)

    def test_support_from_a_grounded_hypothesis_grounds_its_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.recorded_state(
                tmp_dir,
                [self.hypothesis("H1", 0.5), self.hypothesis("H2")],
                [self.edge("O1", "H2", "leads_to"), self.edge("H2", "H1", "supports", likelihood_ratio=9), self.edge("H1", "CS1", "leads_to")],
            )
            self.ok(self.stop(state_path))

    def test_contradiction_from_an_ungrounded_source_still_weighs_against_grounding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.recorded_state(
                tmp_dir,
                [self.hypothesis("H1", 0.95), self.hypothesis("H2", 0.5)],
                [
                    self.edge("O1", "H1", "supports", likelihood_ratio=2),
                    self.edge("H2", "H1", "contradicts", likelihood_ratio=0.25),
                    self.edge("H1", "CS1", "leads_to"),
                ],
            )
            stopped = self.stop(state_path)
            self.assertEqual(stopped.returncode, 1, stopped.stdout)
            self.assertIn("H1", stopped.stderr)
