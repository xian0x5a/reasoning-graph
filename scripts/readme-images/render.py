# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright>=1.48"]
# ///
"""Rebuild the README screenshots of state.html from the example in ./example.

Run from anywhere: `uv run scripts/readme-images/render.py`.
Uses the system Chrome (Playwright channel "chrome"), so no browser download is needed.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
EXAMPLE_DIR = SCRIPT_DIR / "example"
IMAGES_DIR = REPO_ROOT / "docs" / "images"
PACKAGE_DIR = REPO_ROOT / "packages" / "reasoning-graph"

GOAL = "Find why the pumping station went offline at 02:15"
ANSWER_ID = "CS1"
VIEWPORT = {"width": 1300, "height": 1000}
DEVICE_SCALE_FACTOR = 1.5
# Mermaid lays out the graph after load, from a CDN script.
GRAPH_RENDER_TIMEOUT_MS = 30_000


def reasoning_graph(*args: str, cwd: Path) -> None:
    command = ["uv", "--project", str(PACKAGE_DIR), "run", "-q", "reasoning-graph", *args]
    subprocess.run(command, cwd=cwd, check=True)


def build_state(work_dir: Path) -> Path:
    """Copy the example sources so `record` can verify each quote against its file."""
    shutil.copytree(EXAMPLE_DIR, work_dir, dirs_exist_ok=True)
    reasoning_graph("init", "--goal", GOAL, "-o", "state.json", cwd=work_dir)
    reasoning_graph("record", "state.json", "--patch", "patch.json", cwd=work_dir)
    reasoning_graph("audit", "state.json", cwd=work_dir)
    return work_dir / "state.html"


def screenshot_case(page: Page, output: Path) -> None:
    """The answer header and the case for it, as one image."""
    top = page.locator("header.hero").bounding_box()
    bottom = page.locator("#case-section").bounding_box()
    margin = 16
    page.screenshot(
        path=output,
        full_page=True,
        clip={
            "x": top["x"] - margin,
            "y": top["y"] - margin,
            "width": top["width"] + 2 * margin,
            "height": bottom["y"] + bottom["height"] - top["y"] + 2 * margin,
        },
    )


def screenshot_canvas(page: Page, output: Path) -> None:
    """The audit graph with the answer's evidence path focused."""
    page.select_option("[data-candidate-focus-select]", ANSWER_ID)
    page.locator("#audit-graph").screenshot(path=output)


def main() -> None:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="rg-readme-images-") as tmp:
        state_html = build_state(Path(tmp))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome")
            page = browser.new_page(viewport=VIEWPORT, device_scale_factor=DEVICE_SCALE_FACTOR)
            page.goto(state_html.as_uri())
            page.wait_for_selector("#audit-graph svg", timeout=GRAPH_RENDER_TIMEOUT_MS)
            # The floating Sections button would sit on top of the captured cards.
            page.add_style_tag(content=".floating-nav { display: none; }")
            screenshot_case(page, IMAGES_DIR / "state-html-case.png")
            screenshot_canvas(page, IMAGES_DIR / "state-html-canvas.png")
            browser.close()


if __name__ == "__main__":
    main()
