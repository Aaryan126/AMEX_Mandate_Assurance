from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .annotations import (
    AnnotationDecision,
    AnnotationItem,
    AnnotationProgress,
    AnnotationReview,
    configured_annotation_store,
)
from .config import settings
from .database import create_schema, get_session
from .demo_evidence import DemoScenario, signed_demo_cart
from .errors import DomainError
from .schemas import (
    AuditTimeline,
    CartEvidence,
    ConfirmMandateRequest,
    DecisionResponse,
    ErrorDetail,
    ErrorResponse,
    EvaluateDecisionRequest,
    EvaluationSummary,
    InterpretationResponse,
    InterpretMandateRequest,
    MandateView,
    ResolutionResponse,
    ResolveDecisionRequest,
    RevocationResponse,
    RuntimeStatus,
)
from .service import (
    confirm_mandate,
    evaluate_decision,
    evaluation_summary,
    get_audit_timeline,
    get_mandate,
    interpret_mandate,
    resolve_decision,
    revoke_mandate,
    runtime_status,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_schema()
    if settings.model_mode == "development_artifact":
        runtime_status()
    yield


app = FastAPI(
    title="ACE Mandate Assurance API",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    value = request.headers.get("x-correlation-id", f"cor_{uuid4().hex[:16]}")
    request.state.correlation_id = value
    try:
        content_length = int(request.headers.get("content-length", "0") or 0)
    except ValueError:
        content_length = 0
    if content_length > 1_048_576:
        response = ErrorResponse(
            error=ErrorDetail(
                code="REQUEST_TOO_LARGE",
                message="Request bodies are limited to 1 MiB.",
                correlation_id=value,
            )
        )
        return JSONResponse(status_code=413, content=response.model_dump(mode="json"))
    response = await call_next(request)
    response.headers["x-correlation-id"] = value
    return response


@app.exception_handler(DomainError)
async def domain_error_handler(request: Request, exc: DomainError):
    response = ErrorResponse(
        error=ErrorDetail(
            code=exc.code,
            message=exc.message,
            correlation_id=request.state.correlation_id,
            details=exc.details,
        )
    )
    return JSONResponse(status_code=exc.status_code, content=response.model_dump(mode="json"))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    response = ErrorResponse(
        error=ErrorDetail(
            code="VALIDATION_ERROR",
            message="The request did not match the versioned API contract.",
            correlation_id=request.state.correlation_id,
            details={"errors": exc.errors()},
        )
    )
    return JSONResponse(status_code=422, content=response.model_dump(mode="json"))


def idempotency_key(
    value: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=200),
) -> str:
    return value


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "schema_version": settings.schema_version}


@app.get("/v1/runtime/status", response_model=RuntimeStatus)
def runtime_status_route() -> RuntimeStatus:
    return runtime_status()


@app.get("/v1/demo/carts/{scenario}", response_model=CartEvidence)
def demo_cart_route(scenario: DemoScenario, stateful_part: int = Query(default=1, ge=1, le=2)) -> CartEvidence:
    return signed_demo_cart(scenario, stateful_part)


@app.post("/v1/mandates/interpret", response_model=InterpretationResponse)
def interpret_route(request: InterpretMandateRequest) -> InterpretationResponse:
    return interpret_mandate(request)


@app.post("/v1/mandates", response_model=MandateView, status_code=201)
def confirm_route(
    request: ConfirmMandateRequest,
    key: str = Depends(idempotency_key),
    session: Session = Depends(get_session),
) -> MandateView:
    return confirm_mandate(session, request, key)


@app.get("/v1/mandates/{mandate_id}", response_model=MandateView)
def mandate_route(mandate_id: str, session: Session = Depends(get_session)) -> MandateView:
    return get_mandate(session, mandate_id)


@app.post("/v1/mandates/{mandate_id}/revoke", response_model=RevocationResponse)
def revoke_route(
    mandate_id: str,
    key: str = Depends(idempotency_key),
    session: Session = Depends(get_session),
) -> RevocationResponse:
    return revoke_mandate(session, mandate_id, key)


@app.post("/v1/decisions/evaluate", response_model=DecisionResponse)
def evaluate_route(
    request: EvaluateDecisionRequest,
    key: str = Depends(idempotency_key),
    session: Session = Depends(get_session),
) -> DecisionResponse:
    return evaluate_decision(session, request, key)


@app.post("/v1/decisions/{decision_id}/resolve", response_model=ResolutionResponse)
def resolve_route(
    decision_id: str,
    request: ResolveDecisionRequest,
    key: str = Depends(idempotency_key),
    session: Session = Depends(get_session),
) -> ResolutionResponse:
    return resolve_decision(session, decision_id, request, key)


@app.get("/v1/sessions/{session_id}/audit", response_model=AuditTimeline)
def audit_route(session_id: str, session: Session = Depends(get_session)) -> AuditTimeline:
    return get_audit_timeline(session, session_id)


@app.get("/v1/evaluation/summary", response_model=EvaluationSummary)
def evaluation_route() -> EvaluationSummary:
    return evaluation_summary()


@app.get("/internal/annotations/next", response_model=AnnotationItem | None)
def next_annotation_route(
    reviewer_id: str,
    adjudication_only: bool = False,
) -> AnnotationItem | None:
    return configured_annotation_store().next_item(reviewer_id, adjudication_only=adjudication_only)


@app.post("/internal/annotations/{example_id}/reviews", status_code=201)
def review_annotation_route(example_id: str, review: AnnotationReview) -> dict[str, str]:
    try:
        configured_annotation_store().submit_review(example_id, review)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="annotation example not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "recorded"}


@app.post("/internal/annotations/{example_id}/adjudicate", status_code=201)
def adjudicate_annotation_route(example_id: str, decision: AnnotationDecision) -> dict[str, str]:
    try:
        configured_annotation_store().adjudicate(example_id, decision)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "recorded"}


@app.get("/internal/annotations/progress", response_model=AnnotationProgress)
def annotation_progress_route() -> AnnotationProgress:
    return configured_annotation_store().progress()


web_static_value = os.getenv("ACE_WEB_STATIC_DIR")
if web_static_value:
    web_static_dir = Path(web_static_value).resolve()
    if not (web_static_dir / "index.html").is_file():
        raise RuntimeError(f"ACE_WEB_STATIC_DIR does not contain an exported web application: {web_static_dir}")
    app.mount("/", StaticFiles(directory=web_static_dir, html=True), name="web")
