"""Stop gates learned from the Spooky Manor run: unanswered goals (#29), answer-to-candidate
matching (#30), strict test results (#31), and on-graph branching (#32)."""

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
    "frontier": [{"id": "Q1", "node": "T1", "cost_components": {"truth": "auto", "verification": 0.2}}],
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
    "frontier": [{"id": "Q2", "node": "T2", "cost_components": {"truth": "auto", "verification": 0.3}}],
}


class SpookyManorFlow(unittest.TestCase):
    """Drive a strict two-room trail up to the room 2 decode."""

    def start_trail(self, tmp_dir: str) -> Path:
        state_path = Path(tmp_dir) / "state.json"
        self.assertEqual(run_cli("init", "--goal", "Find the URL path into the manor", "--strict", "-o", str(state_path)).returncode, 0)
        self.ok(run_cli("seed", str(state_path), "--patch", str(write_json(Path(tmp_dir) / "seed.json", ROOM_SEED))))
        self.ok(run_cli("next", str(state_path), "--pop"))
        self.ok(run_cli("expand", str(state_path), "--item", "Q1", "--patch", str(write_json(Path(tmp_dir) / "room1.json", ROOM_ONE_SOLVED))))
        self.ok(run_cli("next", str(state_path), "--pop"))
        return state_path

    def ok(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)

    def expand(self, tmp_dir: str, state_path: Path, item: str, patch: dict) -> subprocess.CompletedProcess[str]:
        return run_cli("expand", str(state_path), "--item", item, "--patch", str(write_json(Path(tmp_dir) / f"{item}.json", patch)))


class UnansweredGoalTests(SpookyManorFlow):
    PROFILE_ONLY = {
        "nodes": [{"id": "E4", "type": "observation", "text": "Spectral profile shows 20 tracks", "source": "fft", "prior": 1.0}],
        "edges": [{"id": "T2-E4", "from": "T2", "to": "E4", "type": "leads_to", "reasoning": "The probe produced this profile."}],
        "no_new_work_reason": "Profile recorded; decode reasoning continues off-graph.",
    }

    def test_solved_stop_is_rejected_while_an_accepted_goal_is_unanswered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start_trail(tmp_dir)
            self.ok(self.expand(tmp_dir, state_path, "Q2", self.PROFILE_ONLY))
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
            self.ok(self.expand(tmp_dir, state_path, "Q2", self.PROFILE_ONLY))
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
            self.ok(self.expand(tmp_dir, state_path, "Q2", self.PROFILE_ONLY))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["goal_policy"] = {"optional_goals": ["G2"]}
            write_json(state_path, state)

            stopped = run_cli("stop", str(state_path), "--reason", "G1 answered; G2 optional", "--outcome", "solved", "-o", str(Path(tmp_dir) / "stopped.json"))

            self.ok(stopped)

    def test_stop_review_and_audit_name_the_unanswered_goal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start_trail(tmp_dir)
            self.ok(self.expand(tmp_dir, state_path, "Q2", self.PROFILE_ONLY))
            state = json.loads(state_path.read_text(encoding="utf-8"))
            # Forge the terminal events by hand to bypass the CLI preflight.
            step = state["events"][-1]["step"]
            state["events"].extend([
                {"step": step + 1, "action": "rank", "item": "Q2", "best": "CS1", "belief": 0.95, "candidates": [{"node": "CS1", "belief": 0.95, "effective_truth_cost": 0.051293}]},
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
    def test_strict_test_expansion_requires_a_result_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start_trail(tmp_dir)
            before = state_path.read_text(encoding="utf-8")

            no_result = self.expand(tmp_dir, state_path, "Q2", {
                "nodes": [{"id": "A3", "type": "hypothesis", "text": "Maybe ITA2", "prior": 0.4}],
                "edges": [{"id": "T2-A3", "from": "T2", "to": "A3", "type": "prompts", "reasoning": "The decode attempt suggests ITA2."}],
                "frontier": [{"id": "Q3", "node": "A3", "cost_components": {"truth": "auto"}}],
            })

            self.assertEqual(no_result.returncode, 1, no_result.stdout)
            self.assertIn("expanded test T2 recorded no result", no_result.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_strict_test_expansion_accepts_observation_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start_trail(tmp_dir)
            result = self.expand(tmp_dir, state_path, "Q2", {
                "nodes": [{"id": "O4", "type": "observation", "text": "ITA2 decode gives garbage; URL probe 404", "source": "probe", "prior": 0.95}],
                "edges": [
                    {"id": "T2-O4", "from": "T2", "to": "O4", "type": "leads_to", "reasoning": "The probe produced this result."},
                    {"id": "O4-A2", "from": "O4", "to": "A2", "type": "contradicts", "likelihood_ratio": 0.3, "reasoning": "A failed decode is less likely if the reading is right."},
                ],
                "no_new_work_reason": "Failed probe recorded; sibling interpretations already exhausted for this smoke test.",
            })
            self.ok(result)

    def test_strict_test_expansion_rejects_hypothesis_as_result(self) -> None:
        # A conclusion drawn from a probe is not what was seen; the observation must be recorded first.
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start_trail(tmp_dir)
            before = state_path.read_text(encoding="utf-8")
            result = self.expand(tmp_dir, state_path, "Q2", {
                "nodes": [{"id": "H1", "type": "hypothesis", "text": "The tracks are not ITA2", "prior": 0.9}],
                "edges": [
                    {"id": "T2-H1", "from": "T2", "to": "H1", "type": "leads_to", "reasoning": "The probe suggests this conclusion."},
                    {"id": "H1-A2", "from": "H1", "to": "A2", "type": "contradicts", "likelihood_ratio": 0.3, "reasoning": "Not ITA2 undercuts the 5-bit reading."},
                ],
                "no_new_work_reason": "Conclusion recorded without its observation.",
            })
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("expanded test T2 recorded no result", result.stderr)
            self.assertIn("add an observation node", result.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

    def test_missing_test_result_is_only_a_warning_without_strict_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start_trail(tmp_dir)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["stop_policy"]["severity"] = "warning"
            write_json(state_path, state)

            result = self.expand(tmp_dir, state_path, "Q2", {"no_new_work_reason": "Nothing recorded for this loose run."})

            self.ok(result)
            self.assertIn("expanded test T2 recorded no result", result.stderr)


class OnGraphBranchingTests(SpookyManorFlow):
    OFF_GRAPH_EXPANSION = {
        "nodes": [{"id": "E4", "type": "observation", "text": "Spectral profile shows 20 tracks", "source": "fft", "prior": 1.0}],
        "edges": [{"id": "T2-E4", "from": "T2", "to": "E4", "type": "leads_to", "reasoning": "The probe produced this profile."}],
    }

    def test_strict_expansion_without_new_work_needs_a_recorded_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start_trail(tmp_dir)
            before = state_path.read_text(encoding="utf-8")

            result = self.expand(tmp_dir, state_path, "Q2", self.OFF_GRAPH_EXPANSION)

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("added no frontier work and no candidate", result.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), before)

            with_siblings = self.expand(tmp_dir, state_path, "Q2", {
                **self.OFF_GRAPH_EXPANSION,
                "nodes": self.OFF_GRAPH_EXPANSION["nodes"] + [
                    {"id": "A3", "type": "hypothesis", "text": "Tracks are ITA2 5-bit", "prior": 0.4},
                    {"id": "A4", "type": "hypothesis", "text": "Tracks are A=1..26 with a bit-order permutation", "prior": 0.4},
                ],
                "edges": self.OFF_GRAPH_EXPANSION["edges"] + [
                    {"id": "E4-A3", "from": "E4", "to": "A3", "type": "prompts", "reasoning": "Twenty 5-bit tracks fit ITA2."},
                    {"id": "E4-A4", "from": "E4", "to": "A4", "type": "prompts", "reasoning": "Twenty 5-bit tracks also fit alphabet indexes."},
                ],
                "frontier": [
                    {"id": "Q3", "node": "A3", "cost_components": {"truth": "auto", "verification": 0.2}},
                    {"id": "Q4", "node": "A4", "cost_components": {"truth": "auto", "verification": 0.2}},
                ],
            })
            self.ok(with_siblings)
            frontier = run_cli("frontier", str(state_path))
            self.assertIn("Q3", frontier.stdout)
            self.assertIn("Q4", frontier.stdout)

    def test_audit_reports_peak_live_frontier(self) -> None:
        audit = run_cli("audit", str(FIXTURE))

        self.assertEqual(audit.returncode, 0, audit.stderr)
        self.assertIn("peak_live_frontier=2", audit.stdout)


if __name__ == "__main__":
    unittest.main()
