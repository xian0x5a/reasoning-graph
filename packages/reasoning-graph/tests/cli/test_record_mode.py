"""Queue-free recording: the graph is memory, stop gate, and progress view, not a work queue.

Countdown-island (Muse Spark, n=4 per arm) showed the pop/expand queue adding calls and seeded
rival busywork without improving answers, so `record` writes graph progress directly."""

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
    return {"id": f"{source}-{target}", "from": source, "to": target, "type": edge_type, "reasoning": "Test edge.", **extra}


class RecordModeTests(unittest.TestCase):
    def ok(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)

    def start(self, tmp_dir: str) -> Path:
        state_path = Path(tmp_dir) / "state.json"
        self.ok(run_cli("init", "--goal", "Explain the failure", "--strict", "-o", str(state_path)))
        return state_path

    def record(self, state_path: Path, patch: dict) -> subprocess.CompletedProcess[str]:
        patch_path = state_path.with_name("patch.json")
        patch_path.write_text(json.dumps(patch), encoding="utf-8")
        return run_cli("record", str(state_path), "--patch", str(patch_path))

    def solved_trail(self, state_path: Path, observation_score: int) -> None:
        self.ok(self.record(state_path, {
            "reason": "Ran the probe",
            "nodes": [
                {"id": "T1", "type": "test", "text": "Probe the system"},
                {"id": "O1", "type": "observation", "text": "Probe output", "source": "probe.log", "quote": "exit 3", "note": "Only the last run was logged", "score": observation_score},
            ],
            "edges": [edge("T1", "O1", "leads_to")],
        }))
        self.ok(self.record(state_path, {
            "reason": "Concluded from the probe",
            "nodes": [{"id": "CS1", "type": "candidate_solution", "text": "Root cause", "answer_kind": "exact_answer"}],
            "edges": [edge("O1", "CS1", "leads_to"), edge("CS1", "G1", "answers")],
        }))

    def stop(self, state_path: Path, outcome: str = "solved") -> subprocess.CompletedProcess[str]:
        return run_cli("stop", str(state_path), "--reason", "CS1 is grounded", "--outcome", outcome)

    def test_record_logs_progress_and_renders_live_view(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 5)

            state = json.loads(state_path.read_text(encoding="utf-8"))
            records = [event for event in state["events"] if event["action"] == "record"]
            self.assertEqual([event["reason"] for event in records], ["Ran the probe", "Concluded from the probe"])
            self.assertEqual(records[0]["add_nodes"], ["T1", "O1"])
            live_view = state_path.with_suffix(".html").read_text(encoding="utf-8")
            self.assertIn("CS1", live_view)
            self.assertIn("exit 3", live_view)
            self.assertIn("Only the last run was logged", live_view)

    def test_record_leaves_live_view_untouched_when_the_view_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 5)
            live_view_path = state_path.with_suffix(".html")
            before = live_view_path.stat()

            self.ok(self.record(state_path, {"reason": "Re-read the probe log; nothing new"}))
            unchanged = live_view_path.stat()
            self.assertEqual((unchanged.st_ino, unchanged.st_mtime_ns), (before.st_ino, before.st_mtime_ns))

            self.ok(self.record(state_path, {"reason": "Noted a constraint", "nodes": [{"id": "C1", "type": "constraint", "text": "Keep the API", "source": "user prompt"}]}))
            self.assertIn("Keep the API", live_view_path.read_text(encoding="utf-8"))

    def test_doctor_accepts_a_working_state_and_audits_only_once_stopped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 5)

            working = run_cli("doctor", str(state_path))
            self.ok(working)
            self.assertIn("audit skipped (not stopped)", working.stdout)

            self.ok(self.stop(state_path))
            stopped = run_cli("doctor", str(state_path))
            self.ok(stopped)
            self.assertIn("doctor: audit ok", stopped.stdout)

    def test_record_writes_computed_belief_on_each_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 5)

            nodes = {node["id"]: node for node in json.loads(state_path.read_text(encoding="utf-8"))["nodes"]}
            computed = json.loads(run_cli("beliefs", str(state_path), "--json").stdout)

            self.assertEqual({row["id"]: nodes[row["id"]]["belief"] for row in computed}, {row["id"]: row["belief"] for row in computed})
            self.assertEqual(nodes["O1"]["belief"], 0.9)
            self.assertNotIn("belief", nodes["G1"])
            self.assertNotIn("belief", nodes["T1"])

    def test_record_rejects_an_authored_belief(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 5)

            new_node = self.record(state_path, {"reason": "r", "nodes": [{"id": "H1", "type": "hypothesis", "text": "Guess", "score": 3, "belief": 0.9}]})
            update = self.record(state_path, {"reason": "r", "update_nodes": [{"id": "O1", "set": {"belief": 0.99}}]})

            for rejected in (new_node, update):
                self.assertEqual(rejected.returncode, 1, rejected.stdout)
                self.assertIn("belief", rejected.stderr)

    def test_record_checks_quotes_against_a_local_source_file(self) -> None:
        # Issue #35: stitched or trimmed quotes went unnoticed, so the CLI checks them verbatim.
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            Path(tmp_dir, "case.md").write_text(
                "## Section 8\n\n"
                "- Railing screws partly sawed or filed; not fresh? maybe bright metal visible.\n"
                "- Dr. Saye was seen with Mira, then “checking sedatives” until 20:43.\n\n"
                "> Four bells argue, three bells lie,  \n"
                "> two bells swear, and one asks why.\n",
                encoding="utf-8",
            )

            def observation(node_id: str, quote: str, source: str = "case.md Section 8") -> dict:
                return {"id": node_id, "type": "observation", "text": "Seen in the case file", "source": source, "quote": quote, "score": 5}

            # Line breaks, blockquote markers, quote-mark style, and ellipsis-joined fragments are not edits.
            self.ok(self.record(state_path, {"reason": "Read the case file", "nodes": [
                observation("O1", "Four bells argue, three bells lie, two bells swear"),
                observation("O2", "Railing screws partly sawed or filed ... then 'checking sedatives' until 20:43"),
            ]}))
            # A source that is not a local file cannot be checked and stays free-form.
            self.ok(self.record(state_path, {"reason": "Noted a report", "nodes": [
                observation("O3", "anything", source="https://example.com/report"),
            ]}))

            events_before = len(json.loads(state_path.read_text(encoding="utf-8"))["events"])
            trimmed_hedge = self.record(state_path, {"reason": "r", "nodes": [observation("O4", "Railing screws partly sawed or filed; bright metal visible")]})
            stitched_update = self.record(state_path, {"reason": "r", "update_nodes": [{"id": "O1", "set": {"quote": "Section 8: Railing screws partly sawed"}}]})

            for rejected, node_id in ((trimmed_hedge, "O4"), (stitched_update, "O1")):
                self.assertEqual(rejected.returncode, 1, rejected.stdout)
                self.assertIn(node_id, rejected.stderr)
                self.assertIn("case.md", rejected.stderr)
            self.assertEqual(len(json.loads(state_path.read_text(encoding="utf-8"))["events"]), events_before)

    def test_stale_belief_fails_validation_until_refreshed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 5)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            next(node for node in state["nodes"] if node["id"] == "O1")["score"] = 3
            state_path.write_text(json.dumps(state), encoding="utf-8")

            stale = run_cli("validate", str(state_path))
            self.ok(run_cli("refresh", str(state_path)))
            refreshed = json.loads(state_path.read_text(encoding="utf-8"))

            self.assertEqual(stale.returncode, 1, stale.stdout)
            self.assertIn("stale belief", stale.stderr)
            self.assertIn("refresh", stale.stderr)
            self.ok(run_cli("validate", str(state_path)))
            self.assertEqual(next(node for node in refreshed["nodes"] if node["id"] == "O1")["belief"], 0.5)

    def test_belief_is_only_written_on_claims(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["nodes"][0]["belief"] = 1.0
            state_path.write_text(json.dumps(state), encoding="utf-8")

            result = run_cli("validate", str(state_path))

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("G1", result.stderr)

    def test_record_requires_reason_and_takes_no_frontier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            node = {"id": "T1", "type": "test", "text": "Probe"}

            missing_reason = self.record(state_path, {"nodes": [node]})
            with_frontier = self.record(state_path, {"reason": "r", "nodes": [node], "frontier": [{"id": "Q1", "node": "T1"}]})

            self.assertEqual(missing_reason.returncode, 1)
            self.assertIn("reason", missing_reason.stderr)
            self.assertEqual(with_frontier.returncode, 1)
            self.assertIn("frontier", with_frontier.stderr)

    def test_grounded_answer_stops_and_audits_without_queue_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 5)

            self.ok(self.stop(state_path))
            audit = run_cli("audit", str(state_path))

            self.assertEqual(audit.returncode, 0, audit.stderr)
            self.assertNotIn("warning", audit.stdout + audit.stderr)

    def test_solved_stop_needs_no_belief_level_and_no_review(self) -> None:
        # Issue #37: belief never separated right answers from wrong ones, and a same-model
        # reviewer shared the misreading, so neither gates a stop.
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 3)

            self.ok(self.stop(state_path))
            self.ok(run_cli("audit", str(state_path)))

    def test_solved_stop_needs_every_test_result_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 5)
            self.ok(self.record(state_path, {"reason": "Planned a check", "nodes": [{"id": "T2", "type": "test", "text": "Check the config"}]}))

            stopped = self.stop(state_path)

            self.assertEqual(stopped.returncode, 1, stopped.stdout)
            self.assertIn("T2", stopped.stderr)

    def test_not_run_test_settles_the_result_gate_and_shows_in_the_view(self) -> None:
        # Issue #35: an unrunnable check was answered with an invented result; not_run records it honestly.
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 5)
            self.ok(self.record(state_path, {"reason": "Noted a decisive check nobody can run here", "nodes": [
                {"id": "T2", "type": "test", "text": "Compare dental records", "not_run": "The case file has no dental records"},
            ]}))

            self.ok(self.stop(state_path))
            view = state_path.with_suffix(".html").read_text(encoding="utf-8")
            self.assertIn("not run", view)
            self.assertIn("The case file has no dental records", view)

    def test_not_run_is_only_a_reason_on_a_test_without_a_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.solved_trail(state_path, 5)

            on_hypothesis = self.record(state_path, {"reason": "r", "nodes": [{"id": "H1", "type": "hypothesis", "text": "Guess", "score": 3, "not_run": "x"}]})
            blank_reason = self.record(state_path, {"reason": "r", "nodes": [{"id": "T2", "type": "test", "text": "Check", "not_run": " "}]})
            with_result = self.record(state_path, {"reason": "r", "update_nodes": [{"id": "T1", "set": {"not_run": "Could not run it"}}]})

            for rejected in (on_hypothesis, blank_reason, with_result):
                self.assertEqual(rejected.returncode, 1, rejected.stdout)
                self.assertIn("not_run", rejected.stderr)

    def test_strict_profile_turns_stop_gate_violations_into_audit_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state = json.loads(self.start(tmp_dir).read_text(encoding="utf-8"))

            self.assertEqual(state["stop_policy"], {"severity": "error"})

    def test_removed_review_and_threshold_fields_fail_validation(self) -> None:
        def with_stop_policy(key: str, value: object):
            return lambda state: state["stop_policy"].update({key: value})

        def with_review_event(state: dict) -> None:
            state["events"].append({"step": 99, "action": "review", "reviewer": "r", "verdict": "pass", "findings": "ok", "graph_digest": "x"})

        cases = {
            "stop_policy.require_review": with_stop_policy("require_review", True),
            "stop_policy.belief_threshold": with_stop_policy("belief_threshold", 0.8),
            "review event": with_review_event,
        }
        for removed, edit in cases.items():
            with self.subTest(removed=removed), tempfile.TemporaryDirectory() as tmp_dir:
                state_path = self.start(tmp_dir)
                self.solved_trail(state_path, 5)
                state = json.loads(state_path.read_text(encoding="utf-8"))
                edit(state)
                state_path.write_text(json.dumps(state), encoding="utf-8")

                for command in ("validate", "stop"):
                    arguments = ("--reason", "r", "--outcome", "solved") if command == "stop" else ()
                    rejected = run_cli(command, str(state_path), *arguments)
                    self.assertEqual(rejected.returncode, 1, rejected.stdout)
                    self.assertIn(removed, rejected.stderr)
                    self.assertIn("removed", rejected.stderr)

    def test_review_commands_are_gone(self) -> None:
        for command in ("review", "stop-review"):
            with self.subTest(command=command):
                result = run_cli(command, "state.json")
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("invalid choice", result.stderr)


if __name__ == "__main__":
    unittest.main()
