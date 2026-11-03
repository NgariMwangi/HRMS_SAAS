from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.db.session import dispose_engine, get_engine
from app.middleware import AuditLogMiddleware
from app.middleware.company_domain import CompanyDomainMiddleware
from app.services.domains import backfill_automatic


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    get_engine()
    await backfill_automatic()
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="HRMS SaaS",
        description="Multi-tenant, multi-country HRMS — Day 1 tenancy layer",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_origin_regex=r"https://[a-z0-9-]+\.ngrok(-free)?\.(app|dev|io)",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AuditLogMiddleware)
    app.add_middleware(CompanyDomainMiddleware)
    app.include_router(api_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
