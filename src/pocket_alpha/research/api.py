from uuid import UUID

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy.exc import SQLAlchemyError

from pocket_alpha.common.clock import SystemClock
from pocket_alpha.market_data.api import DB
from pocket_alpha.market_data.quality import DataRejected
from pocket_alpha.research.models import ResearchReport
from pocket_alpha.research.registry import ModelArtifact, ModelRegistry, RegistryEvent
from pocket_alpha.research.storage import ResearchRepository

router = APIRouter(prefix="/api/v1/research", tags=["offline-research"])


@router.get("/reports/{report_id}")
def report(report_id: UUID, db: DB, response: Response) -> ResearchReport:
    response.headers["Cache-Control"] = "no-store"
    try:
        stored = ResearchRepository(db).get(report_id)
        if stored is None:
            raise HTTPException(404, "research report not found")
        return stored
    except (SQLAlchemyError, ValueError, LookupError, StopIteration, DataRejected) as error:
        raise HTTPException(503, "research storage unavailable or invalid") from error


@router.get("/models/{artifact_id}")
def model(
    artifact_id: UUID, db: DB, response: Response
) -> tuple[ModelArtifact, tuple[RegistryEvent, ...]]:
    response.headers["Cache-Control"] = "no-store"
    try:
        stored = ModelRegistry(ResearchRepository(db), SystemClock()).get(artifact_id)
        if stored is None:
            raise HTTPException(404, "research model not found")
        return stored
    except (SQLAlchemyError, ValueError, LookupError, StopIteration, DataRejected) as error:
        raise HTTPException(503, "research storage unavailable or invalid") from error
