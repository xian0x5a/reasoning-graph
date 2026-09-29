"""A source that names a local file links to it from the page, so a reader can open the context
around a quote (#39's reader eval: a reader who could not see the story raised more false alarms).

The link is relative when the file sits under the page's directory, since the two then move
together, and an absolute file URI otherwise."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parents[1]
FIXTURE = PACKAGE_ROOT / "tests" / "fixtures" / "valid" / "reasoning-graph-strict-good.json"
QUOTE = "the fan stopped before the smell"


def run_cli(*args: str, cwd: Path = REPO_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "--project", str(PACKAGE_ROOT), "run", "reasoning-graph", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


class SourceLinkTests(unittest.TestCase):
    def write_state(self, state_dir: Path, source: str) -> Path:
        """The fixture with its one observation citing `source` and quoting it."""
        state = json.loads(FIXTURE.read_text(encoding="utf-8"))
        observation = next(node for node in state["nodes"] if node["id"] == "O1")
        observation.update(source=source, quote=QUOTE)
        state["summary"]["answer"] = "CS1"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_path = state_dir / "state.json"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        return state_path

    def write_source(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"Log: {QUOTE}.\n", encoding="utf-8")

    def render(self, state_path: Path, page_path: Path) -> str:
        page_path.parent.mkdir(parents=True, exist_ok=True)
        result = run_cli("html", str(state_path), "-o", str(page_path))
        self.assertEqual(result.returncode, 0, result.stderr)
        return page_path.read_text(encoding="utf-8")

    def test_source_beside_the_page_links_relatively(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            self.write_source(run_dir / "notes.md")
            page = self.render(self.write_state(run_dir, "notes.md, line 1"), run_dir / "state.html")
        self.assertIn('Source: <a class="source-link" href="notes.md">notes.md</a>, line 1', page)

    def test_source_below_the_page_links_relatively(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            self.write_source(run_dir / "sources" / "notes.md")
            state_path = self.write_state(run_dir, "sources/notes.md")
            page = self.render(state_path, run_dir / "state.html")
        self.assertIn('href="sources/notes.md"', page)

    def test_relative_link_is_url_quoted(self) -> None:
        # Unquoted, "#" would start a fragment and link to a file named "n".
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            self.write_source(run_dir / "n#1.md")
            page = self.render(self.write_state(run_dir, "n#1.md"), run_dir / "state.html")
        self.assertIn('href="n%231.md">n#1.md</a>', page)

    def test_source_outside_the_page_directory_links_absolutely(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir) / "run"
            self.write_source(run_dir / "notes.md")
            state_path = self.write_state(run_dir, "notes.md")
            page = self.render(state_path, Path(tmp_dir) / "pages" / "state.html")
            expected = (run_dir / "notes.md").resolve().as_uri()
        self.assertIn(f'href="{expected}"', page)

    def test_page_on_stdout_links_absolutely(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            self.write_source(run_dir / "notes.md")
            result = run_cli("html", str(self.write_state(run_dir, "notes.md")))
            expected = (run_dir / "notes.md").resolve().as_uri()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'href="{expected}"', result.stdout)

    def test_prose_or_missing_source_stays_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            for source in ("grader feedback", "gone.md"):
                with self.subTest(source=source):
                    page = self.render(self.write_state(run_dir, source), run_dir / "state.html")
                    self.assertIn(f"Source: {source}</p>", page)
                    self.assertNotIn("source-link", page)

    def test_case_quote_cites_a_linked_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            self.write_source(run_dir / "notes.md")
            page = self.render(self.write_state(run_dir, "notes.md"), run_dir / "state.html")
        self.assertIn(f'{QUOTE} <cite><a class="source-link" href="notes.md">notes.md</a></cite>', page)

    def test_record_live_view_links_relatively(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir)
            self.write_source(run_dir / "notes.md")
            state_path = self.write_state(run_dir, "notes.md")
            patch_path = run_dir / "patch.json"
            patch_path.write_text(json.dumps({"nodes": [{"id": "O2", "type": "observation", "text": "Another report"}]}), encoding="utf-8")
            result = run_cli("record", str(state_path), "--patch", str(patch_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            page = state_path.with_suffix(".html").read_text(encoding="utf-8")
        self.assertIn('href="notes.md"', page)

    def test_record_written_elsewhere_links_from_the_new_page(self) -> None:
        # Sources resolve beside the state read; the link starts from the page written with --output.
        with tempfile.TemporaryDirectory() as tmp_dir:
            run_dir = Path(tmp_dir) / "run"
            self.write_source(run_dir / "notes.md")
            state_path = self.write_state(run_dir, "notes.md")
            patch_path = run_dir / "patch.json"
            patch_path.write_text(json.dumps({"nodes": [{"id": "O2", "type": "observation", "text": "Another report"}]}), encoding="utf-8")
            output_path = Path(tmp_dir) / "copy" / "state.json"
            output_path.parent.mkdir()
            result = run_cli("record", str(state_path), "--patch", str(patch_path), "-o", str(output_path))
            self.assertEqual(result.returncode, 0, result.stderr)
            page = output_path.with_suffix(".html").read_text(encoding="utf-8")
            expected = (run_dir / "notes.md").resolve().as_uri()
        self.assertIn(f'href="{expected}"', page)


if __name__ == "__main__":
    unittest.main()
