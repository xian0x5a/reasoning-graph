"""One structured model call through the claude harness, for the rubric drafter and the scorer (issue #37)."""

import json
import subprocess

CALL_TIMEOUT_SECONDS = 300
# The caller holds the gold answer and only judges or drafts text, so it gets no tools
# and none of the default coding-agent prompt.
SYSTEM_PROMPT = "You are a careful grader of detective puzzles. Answer only with the requested JSON."


def structured_call(prompt: str, schema: dict, model: str) -> dict:
    """Return the model's answer as an object matching `schema`. Raises when the call fails."""
    completed = subprocess.run(
        ["claude", "-p", prompt, "--model", model, "--output-format", "json",
         "--no-session-persistence", "--tools", "", "--system-prompt", SYSTEM_PROMPT,
         "--json-schema", json.dumps(schema)],
        capture_output=True, text=True, timeout=CALL_TIMEOUT_SECONDS, check=True,
    )
    result = json.loads(completed.stdout)
    if result["is_error"]:
        raise RuntimeError(f"model call failed: {result['result']}")
    return result["structured_output"]
