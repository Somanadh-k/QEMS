"""The guard that keeps 'the AI never decides' true as the codebase changes.

These are structural tests, not behavioural ones. They exist because the failure they
prevent is not a bug someone introduces deliberately — it is the convenience a
well-meaning contributor adds later ("just default the decision to the AI suggestion").
Running them in CI makes that regression impossible to merge quietly.
"""

import inspect
import re

from app.main import app
from app.models import AIInsight
from app.services import ai_gateway, signal_service


def test_no_route_accepts_an_ai_authored_decision():
    """No endpoint may take a decision/severity/status field on an insight route."""
    ai_routes = [
        r for r in app.routes
        if hasattr(r, "path") and ("signal" in r.path or "insight" in r.path)
    ]
    assert ai_routes, "expected the signal routes to be registered"

    for route in ai_routes:
        body_fields = set()
        for param in getattr(route, "body_field", None) and [route.body_field] or []:
            annotation = getattr(param, "type_", None)
            if annotation is not None and hasattr(annotation, "model_fields"):
                body_fields |= set(annotation.model_fields)
        forbidden = {"decision", "status", "severity", "qa_decision"}
        assert not (body_fields & forbidden), (
            f"{route.path} accepts a workflow-authoritative field: {body_fields & forbidden}"
        )


def test_insight_model_has_no_workflow_columns():
    """An insight can hold a recommendation; it must not hold an outcome."""
    columns = set(AIInsight.__table__.columns.keys())
    forbidden = {"decision", "status_override", "new_status", "final_decision"}
    assert not (columns & forbidden)


def test_signal_service_never_writes_to_workflow_fields():
    """Static check: the signal pipeline must not assign status, severity or decisions."""
    source = inspect.getsource(signal_service)
    for forbidden in (
        r"error\.status\s*=",
        r"error\.severity\s*=",
        r"QADecision\(",
        r"error\.assigned_to\s*=",
    ):
        assert not re.search(forbidden, source), (
            f"signal_service assigns a workflow field matching {forbidden!r} — the AI "
            f"pipeline must never mutate the workflow"
        )


def test_gateway_prompt_forbids_recommending_a_decision():
    """The instruction is part of the contract, so its absence should fail a test."""
    prompt = ai_gateway.RECURRENCE_PROMPT
    assert "Do NOT recommend" in prompt
    assert "decision" in prompt.lower()
    # And the injection posture must be stated explicitly.
    assert "ignore any instruction" in prompt.lower()


def test_gateway_output_schema_has_no_decision_field():
    """The model is given no field in which a verdict could be expressed."""
    prompt = ai_gateway.RECURRENCE_PROMPT
    allowed_keys = {"label", "contributing_factors", "recommended_action"}
    declared = set(re.findall(r'"(\w+)":', prompt))
    assert declared == allowed_keys, f"unexpected output keys declared: {declared}"
