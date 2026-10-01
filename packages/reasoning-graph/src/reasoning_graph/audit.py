"""The one read-only check: the graph, every quote, and the claimed answer.

Nothing is stored about the outcome, so the status cannot go stale: `audit` and the rendered
view compute it from the state they are given (issue #38).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .policy import claimed_answer, unanswered_goal_messages, ungrounded_answer_messages, unnamed_answer_messages, unrecorded_test_messages
from .validation import validate_state


@dataclass
class AuditReport:
    # Whether the answer holds ("checks pass", "1 check fails"), or "no answer claimed".
    outcome: str
    # The outcome with the answer it is about, as `audit` prints it.
    status: str
    errors: list[str]
    warnings: list[str]
    # What an answer would still need, listed while none is claimed.
    needs: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def answer_check_messages(state: dict[str, Any]) -> list[str]:
    """Everything a claimed answer must satisfy; the graph must be valid."""

    return (
        unanswered_goal_messages(state)
        + unnamed_answer_messages(state)
        + ungrounded_answer_messages(state)
        + unrecorded_test_messages(state)
    )


def audit_state(state: dict[str, Any], quote_errors: list[str] | None = None) -> AuditReport:
    """Check the graph and the quotes, and the answer checks once an answer is claimed.

    `quote_errors` come from the caller, which knows where the source files are.
    """

    validation = validate_state(state)
    errors = validation.errors + list(quote_errors or [])
    answer = " ".join(claimed_answer(state).split()) if isinstance(state, dict) else ""
    if not answer:
        # Grounding is judged on a named candidate, so it is not among the needs.
        needs = unanswered_goal_messages(state) + unrecorded_test_messages(state) if validation.ok else []
        return AuditReport(outcome="no answer claimed", status="no answer claimed", errors=errors, warnings=validation.warnings, needs=needs)
    # The answer checks read the graph, so they wait for a valid one.
    errors += answer_check_messages(state) if validation.ok else []
    outcome = "checks pass" if not errors else "1 check fails" if len(errors) == 1 else f"{len(errors)} checks fail"
    return AuditReport(outcome=outcome, status=f"answer {answer}: {outcome}", errors=errors, warnings=validation.warnings, needs=[])
