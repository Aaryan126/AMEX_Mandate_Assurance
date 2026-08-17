from __future__ import annotations

from app.interpreter import interpret
from app.schemas import ConstraintType, InterpretMandateRequest

from .fixtures import OBJECTIVE


def test_interprets_curated_travel_request() -> None:
    response = interpret(InterpretMandateRequest(objective_text=OBJECTIVE))

    by_type = {constraint.type for constraint in response.proposal.constraints}
    assert ConstraintType.TOTAL_BUDGET in by_type
    assert ConstraintType.SEMANTIC_ATTRIBUTE in by_type
    assert ConstraintType.PROHIBITED_ITEM in by_type
    assert ConstraintType.ROUTE in by_type
    budget = next(c for c in response.proposal.constraints if c.type == ConstraintType.TOTAL_BUDGET)
    assert budget.amount_minor == 90000
    assert budget.currency == "SGD"
    assert response.requires_confirmation is True


def test_out_of_template_input_is_flagged_for_review() -> None:
    response = interpret(
        InterpretMandateRequest(objective_text="Find something thoughtful for my colleague tomorrow")
    )
    assert response.warnings
    assert response.proposal.constraints[0].constraint_id == "c_objective"

