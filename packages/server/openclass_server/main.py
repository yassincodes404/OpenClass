from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from openclass_core.discovery import DiscoveryService
from openclass_core.evidence import (
    DiagnosisProvider,
)
from openclass_core.project_evolution import (
    ChoiceTeacher,
    ProjectEvolutionService,
)
from openclass_core.projects import ProjectService as ProjectDomainService
from openclass_core.providers import DecisionProvider, ProviderError, SupervisorProvider
from openclass_core.repositories import ConflictError, NotFoundError
from openclass_core.service import ClassificationService
from openclass_core.supervisor import SupervisorService
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker

from openclass_server.api.candidates import candidates_router
from openclass_server.api.classifiers import classifiers_router
from openclass_server.api.clusters import clusters_router
from openclass_server.api.decisions import decisions_router
from openclass_server.api.evaluations import evaluations_router
from openclass_server.api.evidence import evidence_router
from openclass_server.api.evolution import evolution_router
from openclass_server.api.integrations import integration_router
from openclass_server.api.operations import operations_router
from openclass_server.api.projects import projects_router
from openclass_server.api.promotions import promotions_router
from openclass_server.api.support import support_router
from openclass_server.api.providers import providers_router
from openclass_server.api.system import system_router
from openclass_server.api.unknowns import unknowns_router
from openclass_server.persistence.cluster_store import ClusterStore
from openclass_server.persistence.database import create_database_engine
from openclass_server.persistence.idempotency import IdempotencyStore
from openclass_server.persistence.integration_repository import SQLIntegrationRepository
from openclass_server.persistence.project_repository import SQLProjectRepository
from openclass_server.persistence.promotion_store import PromotionStore
from openclass_server.persistence.repository import SQLRepository
from openclass_server.persistence.unknown_triage import UnknownTriageStore
from openclass_server.provider_config import decision_provider as configured_decision
from openclass_server.provider_config import discovery_provider as configured_discovery
from openclass_server.provider_config import project_diagnosis_provider as configured_diagnosis
from openclass_server.provider_config import project_teacher_provider as configured_teacher
from openclass_server.provider_config import supervisor_provider as configured_supervisor
from openclass_server.rate_limit import RateLimiter
from openclass_server.settings import EXPECTED_SCHEMA_REVISION, Settings


def create_app(
    settings: Settings | None = None,
    provider: DecisionProvider | None = None,
    supervisor_provider: SupervisorProvider | None = None,
    choice_teacher: ChoiceTeacher | None = None,
    diagnosis_provider: DiagnosisProvider | None = None,
) -> FastAPI:
    config = settings or Settings()
    engine = create_database_engine(config, pool_pre_ping=True)
    repository = SQLRepository(async_sessionmaker(engine, expire_on_commit=False))
    default_decision_provider = provider if provider is not None else configured_decision(config)
    service = ClassificationService(
        repository,
        default_decision_provider,
        config.novelty,
    )
    supervisor = SupervisorService(
        repository,
        supervisor_provider if supervisor_provider is not None else configured_supervisor(config),
    )
    discovery = DiscoveryService(repository, configured_discovery(config))
    project_repository = SQLProjectRepository(async_sessionmaker(engine, expire_on_commit=False))
    integration_repository = SQLIntegrationRepository(
        async_sessionmaker(engine, expire_on_commit=False)
    )
    projects = ProjectDomainService(project_repository)
    evolution = ProjectEvolutionService(
        project_repository,
        choice_teacher if choice_teacher is not None else configured_teacher(config),
    )
    diagnostician = (
        diagnosis_provider if diagnosis_provider is not None else configured_diagnosis(config)
    )

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

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default validation response echoes submitted values.
        return JSONResponse(status_code=422, content={"detail": "Invalid request"})

    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def conflict(request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def value_error(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(ProviderError)
    async def provider_error(request: Request, exc: ProviderError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": "Decision provider failed"})

    @app.exception_handler(TimeoutError)
    @app.exception_handler(OSError)
    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": "Database unavailable"})

    limiter = RateLimiter(
        ingest_per_minute=config.rate_limit_ingest_per_minute,
        classify_per_minute=config.rate_limit_classify_per_minute,
        enabled=config.rate_limits_enabled,
    )

    @app.middleware("http")
    async def rate_limit_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        client = request.client.host if request.client else "unknown"
        allowed, retry_after, limit, remaining = limiter.check(client, request.url.path)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded; slow down and retry"},
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )
        response = await call_next(request)
        if limit:
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

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

    app.include_router(classifiers_router(config, repository, service, supervisor, discovery))
    app.include_router(
        projects_router(
            config,
            projects,
            project_repository,
            IdempotencyStore(async_sessionmaker(engine, expire_on_commit=False)),
        )
    )
    app.include_router(evolution_router(config, projects, project_repository, evolution))
    app.include_router(
        decisions_router(config, projects, default_decision_provider, project_repository)
    )
    app.include_router(evidence_router(config, projects, project_repository, diagnostician))
    app.include_router(providers_router(config, async_sessionmaker(engine, expire_on_commit=False)))
    # Literal support routes (adapters/routes/outcomes) register before the
    # parameterized Genesis integration routes so /{integration_id} cannot
    # shadow them.
    app.include_router(
        support_router(
            config,
            projects,
            async_sessionmaker(engine, expire_on_commit=False),
            default_decision_provider,
        )
    )
    app.include_router(integration_router(config, projects, integration_repository))
    app.include_router(system_router(config, engine))
    # Literal cluster routes register before the parameterized unknowns routes
    # so /unknowns/{run_id} cannot shadow them.
    triage_store = UnknownTriageStore(async_sessionmaker(engine, expire_on_commit=False))
    app.include_router(
        clusters_router(
            config,
            projects,
            ClusterStore(async_sessionmaker(engine, expire_on_commit=False)),
            triage_store,
        )
    )
    app.include_router(unknowns_router(config, projects, triage_store))
    app.include_router(
        candidates_router(
            config, projects, async_sessionmaker(engine, expire_on_commit=False), triage_store
        )
    )
    app.include_router(
        evaluations_router(
            config, projects, async_sessionmaker(engine, expire_on_commit=False), triage_store
        )
    )
    app.include_router(
        operations_router(
            config, projects, async_sessionmaker(engine, expire_on_commit=False), triage_store
        )
    )
    app.include_router(
        support_router(
            config,
            projects,
            async_sessionmaker(engine, expire_on_commit=False),
            default_decision_provider,
        )
    )
    app.include_router(
        promotions_router(
            config,
            projects,
            async_sessionmaker(engine, expire_on_commit=False),
            PromotionStore(async_sessionmaker(engine, expire_on_commit=False)),
        )
    )
    return app
