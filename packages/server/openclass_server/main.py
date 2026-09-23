from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from openclass_core.models import (
    ClassificationRecord,
    ClassificationResult,
    Classifier,
    Observation,
    OntologyVersion,
    SupervisorReview,
    UnknownEvent,
)
from openclass_core.providers import DecisionProvider, ProviderError, SupervisorProvider
from openclass_core.repositories import ConflictError, NotFoundError
from openclass_core.service import ClassificationService
from openclass_core.supervisor import SupervisorService
from openclass_provider_mock import MockDecisionProvider, MockSupervisorProvider
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker

from openclass_server.api.schemas import ClassifyRequest, CreateClassifier, CreateReview
from openclass_server.persistence.database import create_database_engine
from openclass_server.persistence.repository import SQLRepository
from openclass_server.settings import EXPECTED_SCHEMA_REVISION, Settings


def create_app(
    settings: Settings | None = None,
    provider: DecisionProvider | None = None,
    supervisor_provider: SupervisorProvider | None = None,
) -> FastAPI:
    config = settings or Settings()
    engine = create_database_engine(config, pool_pre_ping=True)
    repository = SQLRepository(async_sessionmaker(engine, expire_on_commit=False))
    service = ClassificationService(repository, provider or MockDecisionProvider(), config.novelty)
    supervisor = SupervisorService(repository, supervisor_provider or MockSupervisorProvider())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title="OpenClass",
        version="0.0.1",
        lifespan=lifespan,
        description="Genesis API: local, text-only classification with persistent UNKNOWN.",
    )

    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def conflict(request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ProviderError)
    async def provider_error(request: Request, exc: ProviderError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": "Decision provider failed"})

    @app.exception_handler(TimeoutError)
    @app.exception_handler(OSError)
    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": "Database unavailable"})

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.0.1"}

    @app.get("/health/ready")
    async def ready() -> JSONResponse:
        try:
            async with engine.connect() as connection:
                revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
                if revision != EXPECTED_SCHEMA_REVISION:
                    return JSONResponse(status_code=503, content={"status": "migration_required"})
                if engine.dialect.name == "postgresql":
                    vector = await connection.scalar(
                        text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                    )
                    if not vector:
                        return JSONResponse(status_code=503, content={"status": "vector_missing"})
        except (SQLAlchemyError, TimeoutError, OSError):
            return JSONResponse(status_code=503, content={"status": "database_unavailable"})
        return JSONResponse(content={"status": "ready", "schema": EXPECTED_SCHEMA_REVISION})

    @app.post("/api/v1/classifiers", response_model=Classifier, status_code=201)
    async def create_classifier(body: CreateClassifier) -> Classifier:
        return await service.create_classifier(
            **body.model_dump(exclude={"classes"}), classes=body.classes, actor="local-user"
        )

    @app.get("/api/v1/classifiers", response_model=list[Classifier])
    async def classifiers() -> list[Classifier]:
        return await repository.list_classifiers()

    @app.get("/api/v1/classifiers/{identifier}", response_model=Classifier)
    async def classifier(identifier: str) -> Classifier:
        return await repository.get_classifier(identifier)

    @app.post("/api/v1/classifiers/{identifier}/classify", response_model=ClassificationResult)
    async def classify(identifier: str, body: ClassifyRequest) -> ClassificationResult:
        return await service.classify(
            identifier, Observation(content=body.observation, metadata=body.metadata)
        )

    @app.get("/api/v1/classifiers/{identifier}/ontology", response_model=OntologyVersion)
    async def ontology(identifier: str) -> OntologyVersion:
        classifier = await repository.get_classifier(identifier)
        return await repository.get_ontology(classifier.active_ontology_version_id)

    @app.get(
        "/api/v1/classifiers/{identifier}/ontology/versions", response_model=list[OntologyVersion]
    )
    async def versions(identifier: str) -> list[OntologyVersion]:
        classifier = await repository.get_classifier(identifier)
        return await repository.versions(classifier.id)

    @app.get("/api/v1/classifiers/{identifier}/unknowns", response_model=list[UnknownEvent])
    async def unknowns(
        identifier: str,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[UnknownEvent]:
        classifier = await repository.get_classifier(identifier)
        return await repository.unknowns(classifier.id, limit, offset)

    @app.get("/api/v1/classifiers/{identifier}/runs", response_model=list[ClassificationRecord])
    async def runs(
        identifier: str,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[ClassificationRecord]:
        classifier = await repository.get_classifier(identifier)
        return await repository.list_classifications(classifier.id, limit, offset)

    @app.get("/api/v1/classifiers/{identifier}/runs/{run_id}", response_model=ClassificationRecord)
    async def run(identifier: str, run_id: UUID) -> ClassificationRecord:
        classifier = await repository.get_classifier(identifier)
        return await repository.get_classification(classifier.id, run_id)

    @app.post(
        "/api/v1/classifiers/{identifier}/runs/{run_id}/reviews",
        response_model=SupervisorReview,
        status_code=201,
    )
    async def create_review(
        identifier: str, run_id: UUID, body: CreateReview | None = None
    ) -> SupervisorReview:
        try:
            return await supervisor.review_run(identifier, run_id, actor="local-user")
        except ProviderError as exc:
            raise HTTPException(status_code=502, detail="Supervisor provider failed") from exc

    @app.get("/api/v1/classifiers/{identifier}/reviews", response_model=list[SupervisorReview])
    async def reviews(
        identifier: str,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> list[SupervisorReview]:
        classifier = await repository.get_classifier(identifier)
        return await repository.supervisor_reviews(classifier.id, limit, offset)

    @app.get("/api/v1/classifiers/{identifier}/events")
    async def events(
        identifier: str,
        after: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> list[dict[str, Any]]:
        classifier = await repository.get_classifier(identifier)
        return [
            {"sequence": sequence, "event": event.model_dump(mode="json")}
            for sequence, event in await repository.events(classifier.id, after, limit)
        ]

    @app.get("/api/v1/providers")
    async def providers() -> list[dict[str, Any]]:
        return [
            {
                "name": "mock",
                "model": "lexical-demo-v1",
                "simulated": True,
                "capabilities": ["choice"],
            },
            {
                "name": "mock-supervisor",
                "model": "advisory-demo-v1",
                "simulated": True,
                "capabilities": ["review"],
            },
        ]

    return app
