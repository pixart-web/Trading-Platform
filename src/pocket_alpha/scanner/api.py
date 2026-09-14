from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response

from pocket_alpha.common.clock import SystemClock
from pocket_alpha.market_data.api import DB
from pocket_alpha.scanner.models import ScanReport, ScanRequest
from pocket_alpha.scanner.service import ScannerService
from pocket_alpha.scanner.storage import ConflictingScanReport, ScannerRepository

router = APIRouter(prefix="/api/v1/scans", tags=["scanner"])
Limit = Annotated[int, Query(ge=1, le=100)]


@router.post("")
def create_scan(payload: ScanRequest, db: DB, response: Response) -> ScanReport:
    response.headers["Cache-Control"] = "no-store"
    try:
        report = ScannerService(ScannerRepository(db), SystemClock()).scan(payload)
        db.commit()
        return report
    except (ValueError, ConflictingScanReport) as error:
        db.rollback()
        status = 409 if isinstance(error, ConflictingScanReport) else 422
        raise HTTPException(status, str(error)) from error


@router.get("")
def recent_scans(db: DB, response: Response, limit: Limit = 20) -> tuple[ScanReport, ...]:
    response.headers["Cache-Control"] = "no-store"
    return ScannerRepository(db).recent(limit)


@router.get("/{scan_id}")
def scan(scan_id: UUID, db: DB, response: Response) -> ScanReport:
    response.headers["Cache-Control"] = "no-store"
    try:
        return ScannerRepository(db).get(scan_id)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
