from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .auth import sign_proposal
from .config import settings
from .errors import DomainError, NotFoundError
from .explanations import explain
from .interpreter import interpret
from .models import (
    AuditEventRecord,
    CartLineItemRecord,
    CartRecord,
    DecisionRecord,
    DecisionSignalRecord,
    IdempotencyRecord,
    MandateConstraintRecord,
    MandateRecord,
    MandateStateRecord,
    ResolutionRecord,
)
from .policy import apply_policy
from .rules import evaluate_rules
from .schemas import (
    AuditEvent,
    AuditTimeline,
    ConfirmMandateRequest,
    DecisionResponse,
    EvaluateDecisionRequest,
    EvaluationSummary,
    InterpretationResponse,
    InterpretMandateRequest,
    Mandate,
    MandateProposal,
    MandateState,
    MandateView,
    ModelVersions,
    ResolutionAction,
    ResolutionResponse,
    ResolveDecisionRequest,
    RevocationResponse,
    RuntimeStatus,
    utc_now,
)
from .semantic import SemanticScorer, configured_semantic_scorer
from .structured import configured_structured_scorer


def _json(value) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def request_hash(value) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def get_idempotent(session: Session, scope: str, key: str, request_value, response_type):
    record = session.scalar(
        select(IdempotencyRecord).where(IdempotencyRecord.scope == scope, IdempotencyRecord.key == key)
    )
    if record is None:
        return None
    if record.request_hash != request_hash(request_value):
        raise DomainError(
            "IDEMPOTENCY_CONFLICT",
            "The idempotency key was already used with a different request payload.",
            409,
        )
    return response_type.model_validate_json(record.response_json)


def store_idempotent(
    session: Session, scope: str, key: str, request_value, response_value, status_code: int = 200
) -> None:
    session.add(
        IdempotencyRecord(
            scope=scope,
            key=key,
            request_hash=request_hash(request_value),
            response_json=response_value.model_dump_json(),
            status_code=status_code,
            created_at=utc_now(),
        )
    )


def _audit(session: Session, session_id: str, event_type: str, payload: dict) -> AuditEvent:
    event = AuditEvent(
        event_id=f"evt_{uuid4().hex[:16]}",
        session_id=session_id,
        event_type=event_type,
        payload=payload,
        created_at=utc_now(),
    )
    session.add(
        AuditEventRecord(
            id=event.event_id,
            session_id=session_id,
            event_type=event_type,
            payload_json=_json(payload),
            created_at=event.created_at,
        )
    )
    return event


def interpret_mandate(request: InterpretMandateRequest) -> InterpretationResponse:
    return interpret(request)


def _create_mandate(
    session: Session,
    proposal: MandateProposal,
    *,
    superseded_reference: str | None = None,
) -> MandateView:
    if session.get(MandateRecord, proposal.mandate_id):
        raise DomainError("MANDATE_EXISTS", "A mandate with this ID already exists.", 409)
    authenticated_at = utc_now()
    authorization_reference = sign_proposal(proposal, authenticated_at)
    mandate = Mandate(
        **proposal.model_dump(),
        authorization_reference=authorization_reference,
        authenticated_at=authenticated_at,
        superseded_mandate_reference=superseded_reference,
    )
    state = MandateState(
        mandate_id=mandate.mandate_id,
        current_version=mandate.mandate_version,
        status="active",
        last_updated_at=authenticated_at,
    )
    session.add(
        MandateRecord(
            id=mandate.mandate_id,
            version=mandate.mandate_version,
            principal_id=mandate.principal_id,
            agent_id=mandate.agent_id,
            payload_json=mandate.model_dump_json(),
            authorization_reference=authorization_reference,
            status="active",
            authenticated_at=authenticated_at,
            created_at=authenticated_at,
        )
    )
    session.add(
        MandateStateRecord(
            mandate_id=mandate.mandate_id,
            current_version=mandate.mandate_version,
            status="active",
            fulfilled_amount_minor=0,
            fulfillment_count=0,
            prior_transaction_ids_json="[]",
            row_version=0,
            last_updated_at=authenticated_at,
        )
    )
    session.add_all(
        [
            MandateConstraintRecord(
                mandate_id=mandate.mandate_id,
                constraint_id=constraint.constraint_id,
                constraint_type=constraint.type.value,
                payload_json=constraint.model_dump_json(),
            )
            for constraint in mandate.constraints
        ]
    )
    _audit(
        session,
        mandate.mandate_id,
        "MANDATE_AUTHENTICATED",
        {
            "mandate_id": mandate.mandate_id,
            "mandate_version": mandate.mandate_version,
            "constraint_count": len(mandate.constraints),
            "authorization_reference": authorization_reference,
        },
    )
    return MandateView(mandate=mandate, state=state)


def confirm_mandate(session: Session, request: ConfirmMandateRequest, idempotency_key: str) -> MandateView:
    cached = get_idempotent(session, "confirm_mandate", idempotency_key, request, MandateView)
    if cached:
        return cached
    if not request.confirmed:
        raise DomainError("CONFIRMATION_REQUIRED", "The mandate must be explicitly confirmed.", 422)
    view = _create_mandate(session, request.proposal)
    store_idempotent(session, "confirm_mandate", idempotency_key, request, view, 201)
    session.commit()
    return view


def get_mandate(session: Session, mandate_id: str) -> MandateView:
    record = session.get(MandateRecord, mandate_id)
    state_record = session.get(MandateStateRecord, mandate_id)
    if not record or not state_record:
        raise NotFoundError("mandate", mandate_id)
    mandate = Mandate.model_validate_json(record.payload_json)
    mandate.status = record.status
    state = MandateState(
        mandate_id=state_record.mandate_id,
        current_version=state_record.current_version,
        status=state_record.status,
        fulfilled_amount_minor=state_record.fulfilled_amount_minor,
        fulfillment_count=state_record.fulfillment_count,
        prior_transaction_ids=json.loads(state_record.prior_transaction_ids_json),
        last_updated_at=state_record.last_updated_at.replace(tzinfo=UTC)
        if state_record.last_updated_at.tzinfo is None
        else state_record.last_updated_at,
    )
    return MandateView(mandate=mandate, state=state)


def revoke_mandate(session: Session, mandate_id: str, idempotency_key: str) -> RevocationResponse:
    request_scope = {"mandate_id": mandate_id}
    cached = get_idempotent(session, "revoke_mandate", idempotency_key, request_scope, RevocationResponse)
    if cached:
        return cached
    mandate = session.get(MandateRecord, mandate_id)
    state = session.get(MandateStateRecord, mandate_id)
    if not mandate or not state:
        raise NotFoundError("mandate", mandate_id)
    if mandate.status != "active":
        raise DomainError("MANDATE_NOT_ACTIVE", "Only an active mandate can be revoked.", 409)
    mandate.status = "revoked"
    state.status = "revoked"
    state.last_updated_at = utc_now()
    response = RevocationResponse(mandate_id=mandate_id, status="revoked", created_at=utc_now())
    _audit(session, mandate_id, "MANDATE_REVOKED", response.model_dump(mode="json"))
    store_idempotent(session, "revoke_mandate", idempotency_key, request_scope, response)
    session.commit()
    return response


def _semantic_scorer() -> SemanticScorer:
    return configured_semantic_scorer()


def runtime_status() -> RuntimeStatus:
    semantic = configured_semantic_scorer()
    structured = configured_structured_scorer()
    return RuntimeStatus(
        runtime_mode=structured.runtime_mode,
        ready=True,
        semantic=semantic.version,
        catboost=structured.catboost_version,
        calibrator=structured.calibrator_version,
        policy=settings.policy_version,
        features=settings.feature_version,
        candidate_status=structured.candidate_status,
        model_step_up_threshold=structured.step_up_threshold,
        evidence_verification="Ed25519 verification required",
    )


def _fulfill(session: Session, state_record: MandateStateRecord, cart_id: str, amount_minor: int) -> None:
    transactions = json.loads(state_record.prior_transaction_ids_json)
    if cart_id in transactions:
        return
    transactions.append(cart_id)
    result = session.execute(
        update(MandateStateRecord)
        .where(
            MandateStateRecord.mandate_id == state_record.mandate_id,
            MandateStateRecord.row_version == state_record.row_version,
        )
        .values(
            prior_transaction_ids_json=_json(transactions),
            fulfilled_amount_minor=state_record.fulfilled_amount_minor + amount_minor,
            fulfillment_count=state_record.fulfillment_count + 1,
            last_updated_at=utc_now(),
            row_version=state_record.row_version + 1,
        )
    )
    if result.rowcount != 1:
        raise DomainError(
            "MANDATE_STATE_CONFLICT",
            "Mandate state changed during evaluation; retry with a new idempotency key.",
            409,
        )
    session.expire(state_record)


def evaluate_decision(session: Session, request: EvaluateDecisionRequest, idempotency_key: str) -> DecisionResponse:
    cached = get_idempotent(session, "evaluate_decision", idempotency_key, request, DecisionResponse)
    if cached:
        return cached
    view = get_mandate(session, request.mandate_id)
    existing_cart = session.get(CartRecord, request.cart.cart_id)
    if existing_cart and existing_cart.payload_json != request.cart.model_dump_json():
        raise DomainError("CART_ID_CONFLICT", "The cart ID is already associated with different evidence.", 409)

    rules = evaluate_rules(view.mandate, view.state, request.cart)
    scorer = _semantic_scorer()
    semantics = scorer.score(view.mandate.constraints, request.cart)
    structured_scorer = configured_structured_scorer()
    expected_semantic_versions = structured_scorer.semantic_model_versions
    if expected_semantic_versions and scorer.version not in expected_semantic_versions:
        raise DomainError(
            "MODEL_VERSION_MISMATCH",
            "The fusion artifact is not bound to the active semantic model version.",
            503,
        )
    structured_probability = structured_scorer.score(view.mandate, view.state, request.cart, rules, semantics)
    policy = apply_policy(
        rules,
        semantics,
        structured_probability,
        structured_scorer.step_up_threshold,
    )
    reason_codes = policy.reason_codes
    card_explanation, reviewer_explanation = explain(reason_codes)
    created_at = utc_now()
    response = DecisionResponse(
        decision_id=f"dec_{uuid4().hex[:16]}",
        mandate_id=request.mandate_id,
        cart_id=request.cart.cart_id,
        treatment=policy.treatment,
        risk_probability=policy.risk_probability,
        structured_risk_probability=structured_probability,
        uncertainty_band=policy.uncertainty_band,
        reason_codes=reason_codes,
        card_member_explanation=card_explanation,
        reviewer_explanation=reviewer_explanation,
        rule_results=rules,
        semantic_results=semantics,
        model_versions=ModelVersions(
            semantic=scorer.version,
            catboost=structured_scorer.catboost_version,
            stacker=structured_scorer.stacker_version,
            calibrator=structured_scorer.calibrator_version,
            policy=settings.policy_version,
            features=settings.feature_version,
            runtime_mode=structured_scorer.runtime_mode,
            candidate_status=structured_scorer.candidate_status,
            model_step_up_threshold=structured_scorer.step_up_threshold,
        ),
        evidence_references=[
            view.mandate.authorization_reference,
            request.cart.evidence_reference,
        ],
        created_at=created_at,
    )
    if not existing_cart:
        session.add(
            CartRecord(
                id=request.cart.cart_id,
                mandate_id=request.mandate_id,
                payload_json=request.cart.model_dump_json(),
                created_at=created_at,
            )
        )
        session.add_all(
            [
                CartLineItemRecord(
                    cart_id=request.cart.cart_id,
                    line_item_id=item.line_item_id,
                    payload_json=item.model_dump_json(),
                )
                for item in request.cart.line_items
            ]
        )
    session.add(
        DecisionRecord(
            id=response.decision_id,
            mandate_id=request.mandate_id,
            cart_id=request.cart.cart_id,
            treatment=response.treatment.value,
            response_json=response.model_dump_json(),
            created_at=created_at,
        )
    )
    session.add_all(
        [
            DecisionSignalRecord(
                decision_id=response.decision_id,
                signal_type="rule",
                signal_key=result.rule_id,
                payload_json=result.model_dump_json(),
            )
            for result in rules
        ]
        + [
            DecisionSignalRecord(
                decision_id=response.decision_id,
                signal_type="semantic",
                signal_key=result.constraint_id,
                payload_json=result.model_dump_json(),
            )
            for result in semantics
        ]
        + [
            DecisionSignalRecord(
                decision_id=response.decision_id,
                signal_type="structured",
                signal_key=structured_scorer.version or "heuristic",
                payload_json=_json({"probability": structured_probability}),
            )
        ]
    )
    if response.treatment.value == "APPROVE":
        state_record = session.get(MandateStateRecord, request.mandate_id)
        assert state_record is not None
        _fulfill(session, state_record, request.cart.cart_id, request.cart.total_amount_minor)
    _audit(
        session,
        request.mandate_id,
        "DECISION_EVALUATED",
        {
            "decision_id": response.decision_id,
            "cart_id": request.cart.cart_id,
            "treatment": response.treatment,
            "risk_probability": response.risk_probability,
            "structured_risk_probability": response.structured_risk_probability,
            "reason_codes": reason_codes,
            "model_versions": response.model_versions.model_dump(mode="json"),
        },
    )
    store_idempotent(session, "evaluate_decision", idempotency_key, request, response)
    session.commit()
    return response


def resolve_decision(
    session: Session,
    decision_id: str,
    request: ResolveDecisionRequest,
    idempotency_key: str,
) -> ResolutionResponse:
    request_scope = {"decision_id": decision_id, "request": request.model_dump(mode="json")}
    cached = get_idempotent(session, "resolve_decision", idempotency_key, request_scope, ResolutionResponse)
    if cached:
        return cached
    decision = session.get(DecisionRecord, decision_id)
    if not decision:
        raise NotFoundError("decision", decision_id)
    if decision.resolved_action:
        raise DomainError("DECISION_ALREADY_RESOLVED", "This decision is already resolved.", 409)
    if decision.treatment != "STEP_UP":
        raise DomainError("DECISION_NOT_RESOLVABLE", "Only step-up decisions can be resolved.", 409)

    new_mandate_id: str | None = None
    if request.action == ResolutionAction.APPROVE_ONCE:
        cart = session.get(CartRecord, decision.cart_id)
        state = session.get(MandateStateRecord, decision.mandate_id)
        assert cart is not None and state is not None
        cart_payload = json.loads(cart.payload_json)
        _fulfill(session, state, cart.id, int(cart_payload["total_amount_minor"]))
    elif request.action == ResolutionAction.MODIFY_MANDATE:
        assert request.modified_proposal is not None
        old_mandate = session.get(MandateRecord, decision.mandate_id)
        old_state = session.get(MandateStateRecord, decision.mandate_id)
        assert old_mandate is not None and old_state is not None
        old_mandate.status = "superseded"
        old_state.status = "superseded"
        proposal = request.modified_proposal.model_copy(update={"mandate_version": old_mandate.version + 1})
        view = _create_mandate(session, proposal, superseded_reference=old_mandate.authorization_reference)
        new_mandate_id = view.mandate.mandate_id

    decision.resolved_action = request.action.value
    response = ResolutionResponse(
        decision_id=decision_id,
        action=request.action,
        status="resolved",
        mandate_id=decision.mandate_id,
        new_mandate_id=new_mandate_id,
        created_at=utc_now(),
    )
    session.add(
        ResolutionRecord(
            id=f"res_{uuid4().hex[:16]}",
            decision_id=decision_id,
            action=request.action.value,
            payload_json=response.model_dump_json(),
            created_at=response.created_at,
        )
    )
    _audit(
        session,
        decision.mandate_id,
        "STEP_UP_RESOLVED",
        response.model_dump(mode="json"),
    )
    store_idempotent(session, "resolve_decision", idempotency_key, request_scope, response)
    session.commit()
    return response


def get_audit_timeline(session: Session, session_id: str) -> AuditTimeline:
    records = session.scalars(
        select(AuditEventRecord).where(AuditEventRecord.session_id == session_id).order_by(AuditEventRecord.created_at)
    ).all()
    if not records:
        raise NotFoundError("session", session_id)
    return AuditTimeline(
        session_id=session_id,
        events=[
            AuditEvent(
                event_id=record.id,
                session_id=record.session_id,
                event_type=record.event_type,
                payload=json.loads(record.payload_json),
                created_at=record.created_at.replace(tzinfo=UTC)
                if record.created_at.tzinfo is None
                else record.created_at,
            )
            for record in records
        ],
    )


def evaluation_summary() -> EvaluationSummary:
    default_report = Path(__file__).resolve().parent.parent / "data" / "development-v3-evaluation-summary.json"
    report_path = Path(os.getenv("ACE_EVALUATION_REPORT", str(default_report)))
    if report_path.exists():
        return EvaluationSummary.model_validate_json(report_path.read_text())
    return EvaluationSummary(
        dataset_version="development-v3-candidate-selection-1000",
        model_version="catboost-v1 + platt-calibrator-v3",
        status="not_run",
        metrics={},
        attack_families={},
        latency_ms={},
        generated_at=datetime(2026, 8, 20, tzinfo=UTC),
    )
