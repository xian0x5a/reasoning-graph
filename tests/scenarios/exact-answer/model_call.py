"""One structured model call through the claude harness, for the rubric drafter, the scorer and the reader eval (issues #37, #39)."""

import json
import subprocess

CALL_TIMEOUT_SECONDS = 300
# The caller holds the gold answer and only judges or drafts text, so it gets no tools
# and none of the default coding-agent prompt.
SYSTEM_PROMPT = "You are a careful grader of detective puzzles. Answer only with the requested JSON."


def model_call(prompt: str, schema: dict, model: str, system_prompt: str = SYSTEM_PROMPT) -> dict:
    """Return the harness's whole result: `structured_output` matches `schema`, and
    `total_cost_usd` is what the call cost. Raises when the call fails."""
    completed = subprocess.run(
        ["claude", "-p", prompt, "--model", model, "--output-format", "json",
         "--no-session-persistence", "--tools", "", "--system-prompt", system_prompt,
         "--json-schema", json.dumps(schema)],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=CALL_TIMEOUT_SECONDS, check=False,
    )
    if completed.returncode and not completed.stdout.strip():
        raise RuntimeError(f"model call failed (exit {completed.returncode}): {completed.stderr.strip()[:300]}")
    result = json.loads(completed.stdout)
    # A refusal by the safety classifier exits 1 with a normal result; its stop reason says why.
    if completed.returncode or result["is_error"]:
        raise RuntimeError(f"model call failed ({result.get('stop_reason')}): {str(result.get('result'))[:300]}")
    return result


def structured_call(prompt: str, schema: dict, model: str) -> dict:
    """Return the model's answer as an object matching `schema`. Raises when the call fails."""
    return model_call(prompt, schema, model)["structured_output"]
