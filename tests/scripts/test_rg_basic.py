import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RG = REPO_ROOT / "skills" / "reasoning-graph" / "scripts" / "rg.py"
FIXTURE = REPO_ROOT / "tests" / "reasoning-graph-strict-good.json"


class ReasoningGraphCliBasicTests(unittest.TestCase):
    def run_rg(self, *args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(RG), *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            **kwargs,
        )

    def test_validate_and_audit_fixture_pass(self) -> None:
        validate = self.run_rg("validate", str(FIXTURE))
        self.assertEqual(validate.returncode, 0, validate.stderr)
        self.assertIn("ok", validate.stdout)

        audit = self.run_rg("audit", str(FIXTURE))
        self.assertEqual(audit.returncode, 0, audit.stderr)
        self.assertIn("ok", audit.stdout)

    def test_costs_writes_computed_frontier_costs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "costs.json"
            result = self.run_rg("costs", str(FIXTURE), "-o", str(output))

            self.assertEqual(result.returncode, 0, result.stderr)
            state = json.loads(output.read_text(encoding="utf-8"))
            frontier = state["frontier"]
            self.assertTrue(frontier)
            self.assertTrue(all("search_cost" in item for item in frontier))
            self.assertTrue(all("truth_cost" in item for item in frontier))

    def test_stop_output_does_not_mutate_input_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            stopped_path = Path(tmp_dir) / "stopped.json"
            original = FIXTURE.read_text(encoding="utf-8")
            state_path.write_text(original, encoding="utf-8")

            result = self.run_rg(
                "stop",
                str(state_path),
                "--reason",
                "test stop",
                "--outcome",
                "user_stopped",
                "-o",
                str(stopped_path),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original)
            stopped = json.loads(stopped_path.read_text(encoding="utf-8"))
            self.assertEqual(stopped["events"][-1]["action"], "stop")
            self.assertEqual(stopped["events"][-1]["outcome"], "user_stopped")

    def test_mermaid_and_html_smoke(self) -> None:
        mermaid = self.run_rg("mermaid", str(FIXTURE))
        self.assertEqual(mermaid.returncode, 0, mermaid.stderr)
        self.assertIn("flowchart", mermaid.stdout)

        with tempfile.TemporaryDirectory() as tmp_dir:
            html_path = Path(tmp_dir) / "graph.html"
            html = self.run_rg("html", str(FIXTURE), "-o", str(html_path))
            self.assertEqual(html.returncode, 0, html.stderr)
            html_text = html_path.read_text(encoding="utf-8")
            self.assertIn("<!doctype html>", html_text.lower())
            self.assertIn("Best explanation graph", html_text)


if __name__ == "__main__":
    unittest.main()
