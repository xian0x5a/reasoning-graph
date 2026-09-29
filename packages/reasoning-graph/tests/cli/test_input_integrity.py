"""Malformed input handling and atomic state writes (#8, #11)."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
FIXTURE = PACKAGE_ROOT / "tests" / "fixtures" / "valid" / "minimal-state.json"


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
    )


class MalformedStateInputTests(unittest.TestCase):
    MALFORMED_DOCUMENTS = {
        "list": ("[]", "state must be an object"),
        "null": ("null", "state must be an object"),
        "bad-score": (
            json.dumps({"nodes": [{"id": "A1", "type": "hypothesis", "score": "high"}], "edges": []}),
            "score",
        ),
    }

    def test_audit_reports_structured_error_for_malformed_documents(self) -> None:
        for label, (document, expected) in self.MALFORMED_DOCUMENTS.items():
            with self.subTest(document=label), tempfile.TemporaryDirectory() as tmp_dir:
                state_path = Path(tmp_dir) / "state.json"
                state_path.write_text(document, encoding="utf-8")

                result = run_cli("audit", str(state_path))

                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("error: schema", result.stderr)
                self.assertIn(expected, result.stderr)
                self.assertNotIn("AttributeError", result.stderr)
                self.assertNotIn("has no attribute", result.stderr)

    def test_audit_fails_cleanly_for_non_object_documents(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            state_path.write_text("[1, 2]", encoding="utf-8")

            result = run_cli("audit", str(state_path))

            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("state must be an object", result.stderr)
            self.assertNotIn("has no attribute", result.stderr)


def record_step(state_path: Path, patch_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    patch_path = patch_path or state_path.with_name("patch.json")
    patch_path.write_text(json.dumps({"answer": ""}), encoding="utf-8")
    return run_cli("record", str(state_path), "--patch", str(patch_path))


class AtomicStateWriteTests(unittest.TestCase):
    def test_in_place_write_leaves_no_temporary_files_and_preserves_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_path = Path(tmp_dir) / "state.json"
            state_path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
            os.chmod(state_path, 0o640)

            result = record_step(state_path)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(sorted(path.name for path in Path(tmp_dir).iterdir()), ["patch.json", "state.html", "state.index.md", "state.json"])
            self.assertEqual(os.stat(state_path).st_mode & 0o777, 0o640)
            json.loads(state_path.read_text(encoding="utf-8"))

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
    def test_failed_write_keeps_original_state_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_dir = Path(tmp_dir) / "locked"
            state_dir.mkdir()
            state_path = state_dir / "state.json"
            original = FIXTURE.read_text(encoding="utf-8")
            state_path.write_text(original, encoding="utf-8")
            os.chmod(state_dir, 0o500)
            try:
                result = record_step(state_path, Path(tmp_dir) / "patch.json")
            finally:
                os.chmod(state_dir, 0o700)

            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertEqual(state_path.read_text(encoding="utf-8"), original)
            self.assertEqual([path.name for path in state_dir.iterdir()], ["state.json"])


if __name__ == "__main__":
    unittest.main()
