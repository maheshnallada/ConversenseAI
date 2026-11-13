from typing import Annotated

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.domain.envelope import InteractionEnvelope
from app.ingestion.errors import IdempotencyConflict
from app.ingestion.service import IngestResult, IngestionService


class IngestResponse(BaseModel):
    created: bool
    interaction: InteractionEnvelope


def create_app(session_factory) -> FastAPI:
    app = FastAPI(title="Health call observability")
    app.state.session_factory = session_factory

    def service() -> IngestionService:
        return IngestionService(session_factory)

    @app.post("/api/v1/interactions", response_model=IngestResponse)
    def ingest_interaction(
        body: InteractionEnvelope,
        x_tenant_id: Annotated[str | None, Header()] = None,
    ):
        if not x_tenant_id:
            raise HTTPException(status_code=401, detail="X-Tenant-Id is required")
        if x_tenant_id != body.tenant_id:
            raise HTTPException(status_code=403, detail="Tenant header does not match body")
        try:
            result: IngestResult = service().ingest(body)
        except IdempotencyConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        status_code = 201 if result.created else 200
        payload = IngestResponse(created=result.created, interaction=result.interaction)
        return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))

    @app.get("/api/v1/interactions/{interaction_id}", response_model=InteractionEnvelope)
    def get_interaction(
        interaction_id: str,
        x_tenant_id: Annotated[str | None, Header()] = None,
    ):
        if not x_tenant_id:
            raise HTTPException(status_code=401, detail="X-Tenant-Id is required")
        found = service().get(x_tenant_id, interaction_id)
        if found is None:
            raise HTTPException(status_code=404, detail="Interaction not found")
        return found

    return app
