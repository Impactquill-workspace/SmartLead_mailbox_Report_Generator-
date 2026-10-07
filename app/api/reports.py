"""
Reports API router.

Endpoints:
  GET  /api/reports/weekly               → Current previous-week report
  GET  /api/reports/weekly?start_date=&end_date=  → Custom period report
  GET  /api/reports/weekly/export        → Download Excel file
  POST /api/reports/generate             → Generate report for any period
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.smartlead_client import SmartleadApiClient
from app.clients.smartlead_exceptions import SmartleadAuthError, SmartleadError
from app.core.config import get_settings
from app.models.database import get_db
from app.schemas.report import GenerateReportRequest, WeeklyReportResponse
from app.services.weekly_report_service import WeeklyReportService
from app.utils.date_utils import get_previous_calendar_week, parse_date

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reports", tags=["Reports"])

_settings = get_settings()


def get_api_client() -> SmartleadApiClient:
    return SmartleadApiClient(_settings)


@router.get("/weekly", response_model=WeeklyReportResponse)
async def get_weekly_report(
    start_date: Optional[str] = Query(
        None,
        description="Start date YYYY-MM-DD. Defaults to previous Monday.",
    ),
    end_date: Optional[str] = Query(
        None,
        description="End date YYYY-MM-DD. Defaults to previous Sunday.",
    ),
    db: AsyncSession = Depends(get_db),
) -> WeeklyReportResponse:
    """
    Generate and return the weekly mailbox report.

    If no dates are provided, uses the previous calendar week (Mon–Sun).
    Custom date ranges are supported via start_date and end_date query params.
    """
    if start_date and end_date:
        try:
            start = parse_date(start_date)
            end = parse_date(end_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    else:
        date_range = get_previous_calendar_week()
        start = date_range.start
        end = date_range.end

    api_client = get_api_client()
    service = WeeklyReportService(
        api_client=api_client,
        db_session=db,
        dry_run=_settings.dry_run,
    )

    try:
        async with api_client:
            report = await service.generate_report(start, end)
        return report
    except SmartleadAuthError as exc:
        logger.error("Smartlead auth failure: %s", exc)
        raise HTTPException(
            status_code=401,
            detail="Smartlead authentication failed. Check SMARTLEAD_API_KEY.",
        )
    except SmartleadError as exc:
        logger.error("Smartlead API error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"Smartlead API error: {exc}",
        )
    except Exception as exc:
        logger.error("Unexpected error generating report: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/weekly/export")
async def export_weekly_report(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """
    Generate the weekly report and return the Excel file for download.
    """
    if start_date and end_date:
        try:
            start = parse_date(start_date)
            end = parse_date(end_date)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    else:
        date_range = get_previous_calendar_week()
        start = date_range.start
        end = date_range.end

    filename = (
        f"weekly_mailbox_report_{start.isoformat()}_to_{end.isoformat()}.xlsx"
    )
    file_path = Path("exports") / filename

    api_client = get_api_client()
    service = WeeklyReportService(
        api_client=api_client,
        db_session=db,
        dry_run=_settings.dry_run,
    )

    try:
        async with api_client:
            await service.generate_report(start, end)
    except SmartleadAuthError:
        raise HTTPException(
            status_code=401,
            detail="Smartlead authentication failed.",
        )
    except SmartleadError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    if not file_path.exists():
        raise HTTPException(
            status_code=404, detail="Report file could not be generated"
        )

    return FileResponse(
        path=str(file_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )


@router.get("/presets")
async def get_report_presets() -> dict[str, Any]:
    """Return common date presets like previous calendar week."""
    from app.utils.date_utils import format_date, get_previous_calendar_week
    last_week = get_previous_calendar_week()
    return {
        "last_week": {
            "start_date": format_date(last_week.start),
            "end_date": format_date(last_week.end),
        }
    }


@router.get("/download/{filename}")
async def download_report_file(filename: str) -> FileResponse:
    """Download an exported report file safely by name."""
    safe_name = Path(filename).name
    file_path = Path("exports") / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Report file not found")
    return FileResponse(
        path=str(file_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=safe_name,
    )


@router.post("/generate", response_model=WeeklyReportResponse)
async def generate_report(
    request: GenerateReportRequest,
    db: AsyncSession = Depends(get_db),
) -> WeeklyReportResponse:
    """
    Manually trigger report generation for a custom date range and filters.

    Body:
        {
            "start_date": "YYYY-MM-DD",
            "end_date": "YYYY-MM-DD",
            "client_id": null | int,
            "status_filter": "ACTIVE" | null
        }
    """
    try:
        start = parse_date(request.start_date)
        end = parse_date(request.end_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    api_client = get_api_client()
    service = WeeklyReportService(
        api_client=api_client,
        db_session=db,
        dry_run=_settings.dry_run,
    )

    try:
        async with api_client:
            return await service.generate_report(
                start,
                end,
                status_filter=request.status_filter,
                client_id_filter=request.client_id,
            )
    except SmartleadAuthError:
        raise HTTPException(
            status_code=401,
            detail="Smartlead authentication failed.",
        )
    except SmartleadError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

