"""`audit` is the one read-only check: the graph, every quote, and the claimed answer (issue #38).

`stop` wrote a certificate and locked the state behind it. In the resume loop of #37 that lock
cost 38 refused writes and 23 hand edits, and the certificate guarded an accuracy gate that no
longer exists. The claim is now `summary.answer`, and its status is computed on demand."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
SOURCE_TEXT = "The gardener signed in at nine. The butler had the key.\n"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )


def edge(source: str, target: str, edge_type: str, **extra: int) -> dict:
    return {"id": f"{source}-{target}", "from": source, "to": target, "type": edge_type, **extra}


def candidate(node_id: str, text: str) -> dict:
    return {"id": node_id, "type": "candidate_solution", "text": text, "answer_kind": "exact_answer"}


# CS1 rests on a quoted observation. CS2 rests on nothing.
STORY_PATCH = {
    "nodes": [
        {"id": "O1", "type": "observation", "text": "The gardener signed in at nine", "source": "problem.md", "quote": "The gardener signed in at nine"},
        candidate("CS1", "The gardener"),
        candidate("CS2", "The butler"),
    ],
    "edges": [edge("O1", "CS1", "leads_to"), edge("CS1", "G1", "answers"), edge("CS2", "G1", "answers")],
}


class AuditCase(unittest.TestCase):
    def ok(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0, result.stderr)

    def fails(self, result: subprocess.CompletedProcess[str], *expected: str) -> None:
        self.assertEqual(result.returncode, 1, result.stdout)
        for text in expected:
            self.assertIn(text, result.stderr)

    def start(self, tmp_dir: str, answer: str | None = None) -> Path:
        state_path = Path(tmp_dir) / "state.json"
        Path(tmp_dir, "problem.md").write_text(SOURCE_TEXT, encoding="utf-8")
        self.ok(run_cli("init", "--goal", "Who did it?", "-o", str(state_path)))
        self.ok(self.record(state_path, STORY_PATCH | ({} if answer is None else {"answer": answer})))
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

    def status(self, result: subprocess.CompletedProcess[str]) -> str:
        return result.stdout.splitlines()[0]


class AuditStatusTests(AuditCase):
    def test_state_without_an_answer_passes_and_lists_what_an_answer_needs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.ok(self.record(state_path, {"nodes": [{"id": "T1", "type": "test", "text": "Ask the cook"}]}))

            audit = run_cli("audit", str(state_path))

            self.ok(audit)
            self.assertEqual(self.status(audit), "no answer claimed")
            self.assertIn("test(s) without a recorded result observation: T1", audit.stdout)
            self.assertEqual(audit.stderr, "")

    def test_a_goals_only_candidate_is_not_its_answer_until_named(self) -> None:
        # A half-finished graph with one candidate would otherwise count as a claim.
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.ok(self.record(state_path, {"remove_nodes": ["CS2"]}))

            audit = run_cli("audit", str(state_path))

            self.ok(audit)
            self.assertEqual(self.status(audit), "no answer claimed")

    def test_grounded_answer_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir, answer="CS1")

            audit = run_cli("audit", str(state_path))

            self.ok(audit)
            self.assertEqual(self.status(audit), "answer CS1: checks pass")

    def test_failed_answer_checks_are_counted_and_fail_the_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir, answer="CS2")
            self.ok(self.record(state_path, {"nodes": [{"id": "T1", "type": "test", "text": "Ask the cook"}]}))

            audit = run_cli("audit", str(state_path))

            self.fails(audit, "answer candidate CS2 is not evidence-grounded", "test(s) without a recorded result observation: T1")
            self.assertEqual(self.status(audit), "answer CS2: 2 checks fail")

    def test_answer_must_name_exactly_one_candidate(self) -> None:
        cases = {
            "The chauffeur did it.": "summary.answer names no candidate for goal G1",
            "CS1 or CS2": "names several candidates for goal G1: CS1, CS2",
            "CS10": "summary.answer names no candidate for goal G1",
        }
        for answer, expected in cases.items():
            with self.subTest(answer=answer), tempfile.TemporaryDirectory() as tmp_dir:
                self.fails(run_cli("audit", str(self.start(tmp_dir, answer=answer))), expected)

    def test_report_answer_must_name_the_candidate_the_claim_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir, answer="CS1")
            self.edit(state_path, lambda state: state.update({"report": {"answer": "The butler"}}))

            self.fails(run_cli("audit", str(state_path)), "report.answer does not name candidate CS1")

    def test_report_answer_alone_is_not_a_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.edit(state_path, lambda state: state.update({"report": {"answer": "CS1"}}))

            self.fails(run_cli("audit", str(state_path)), "report.answer is set while summary.answer is empty")

    def test_draft_must_mention_the_answer_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir, answer="CS1")
            draft = Path(tmp_dir) / "answer.md"
            draft.write_text("Final answer: The butler.", encoding="utf-8")

            self.fails(run_cli("audit", str(state_path), "--draft", str(draft)), "draft does not mention candidate CS1 ('The gardener') for goal G1")

            draft.write_text("Final answer: The gardener. The butler only had the key.", encoding="utf-8")
            self.ok(run_cli("audit", str(state_path), "--draft", str(draft)))

    def test_malformed_graph_and_failed_quote_fail_without_an_answer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.edit(state_path, lambda state: state["nodes"][1].update({"quote": "The gardener signed in at ten"}))
            quote = run_cli("audit", str(state_path))
            self.fails(quote, "O1", "problem.md")
            self.assertEqual(self.status(quote), "no answer claimed")

            self.edit(state_path, lambda state: state["nodes"].append({"id": "X1", "type": "fact", "text": "Legacy"}))
            self.fails(run_cli("audit", str(state_path)), "invalid type 'fact'")

    def test_audit_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir, answer="CS1")
            for view in (".html", ".index.md"):
                state_path.with_suffix(view).unlink()
            before = state_path.read_text(encoding="utf-8")

            self.ok(run_cli("audit", str(state_path)))

            self.assertEqual(state_path.read_text(encoding="utf-8"), before)
            self.assertEqual(sorted(path.name for path in Path(tmp_dir).iterdir()), ["patch.json", "problem.md", "state.json"])


class AnswerIsSetByThePatchTests(AuditCase):
    def test_patch_sets_and_clears_the_answer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)

            self.ok(self.record(state_path, {"answer": " CS1 "}))
            self.assertEqual(self.load(state_path)["summary"]["answer"], "CS1")
            self.assertIn("Answer: CS1", state_path.with_suffix(".index.md").read_text(encoding="utf-8"))

            self.ok(self.record(state_path, {"answer": ""}))
            self.assertEqual(self.load(state_path)["summary"]["answer"], "")

    def test_work_continues_after_an_answer(self) -> None:
        # The user rejects the answer: one patch records what they said and withdraws the claim.
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir, answer="CS1")
            self.ok(run_cli("audit", str(state_path)))

            self.ok(self.record(state_path, {
                "nodes": [
                    {"id": "O2", "type": "observation", "text": "The user says the gardener was abroad", "source": "user"},
                    {"id": "T1", "type": "test", "text": "Check who else had the key"},
                ],
                "edges": [edge("O2", "CS1", "contradicts", score=5), edge("O2", "T1", "prompts")],
                "answer": "",
            }))

            audit = run_cli("audit", str(state_path))
            self.ok(audit)
            self.assertEqual(self.status(audit), "no answer claimed")


class RemovedStopCertificateTests(AuditCase):
    def test_stop_validate_and_doctor_are_gone(self) -> None:
        for command in ("stop", "validate", "doctor"):
            with self.subTest(command=command):
                result = run_cli(command, "state.json")
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn("invalid choice", result.stderr)

    def test_init_takes_no_profile(self) -> None:
        for option in (("--strict",), ("--profile", "strict")):
            with self.subTest(option=option[0]):
                result = run_cli("init", "--goal", "Who did it?", *option)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn(option[0], result.stderr)

        state = json.loads(run_cli("init", "--goal", "Who did it?").stdout)
        self.assertEqual(sorted(state), ["edges", "nodes", "summary"])

    def test_state_carrying_stop_policy_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)
            self.edit(state_path, lambda state: state.update({"stop_policy": {"severity": "error"}}))

            for rejected in (run_cli("audit", str(state_path)), run_cli("refresh", str(state_path)), self.record(state_path, {"answer": "CS1"})):
                self.fails(rejected, "stop_policy was removed")

    def test_patch_takes_no_outcome(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = self.start(tmp_dir)

            self.fails(self.record(state_path, {"answer": "CS1", "outcome": "solved"}), "outcome")


if __name__ == "__main__":
    unittest.main()
