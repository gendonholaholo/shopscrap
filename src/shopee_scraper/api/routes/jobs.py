"""Job endpoints - RESTful resource for job management."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query, status

from shopee_scraper.api.dependencies import RequireApiKey
from shopee_scraper.api.jobs import JobStatus, get_job_queue


router = APIRouter(prefix="/jobs", tags=["Jobs"])


# =============================================================================
# Job Management Endpoints
# =============================================================================


@router.get(
    "",
    summary="List all jobs",
    description="Get list of all jobs with optional status filter.",
)
async def list_jobs(
    _api_key: RequireApiKey,
    status_filter: str | None = Query(
        None,
        alias="status",
        description="Filter by status: pending, processing, completed, failed",
    ),
    limit: int = Query(50, ge=1, le=100, description="Max jobs to return"),
) -> dict[str, Any]:
    """List all jobs."""
    queue = get_job_queue()

    # Parse status filter
    job_status = None
    if status_filter:
        try:
            job_status = JobStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}",
            ) from None

    jobs = await queue.list_jobs(status=job_status, limit=limit)

    return {
        "success": True,
        "meta": {
            "total": len(jobs),
            "limit": limit,
            "status_filter": status_filter,
        },
        "data": [job.to_dict() for job in jobs],
        "links": {
            "self": "/api/v1/jobs",
        },
    }


@router.get(
    "/{job_id}",
    summary="Get job details",
    description="Get full details and results of a job.",
)
async def get_job(
    _api_key: RequireApiKey,
    job_id: str = Path(..., description="Job ID"),
) -> dict[str, Any]:
    """Get job by ID with full details."""
    queue = get_job_queue()
    job = await queue.get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    return {
        "success": True,
        "data": job.to_dict(),
        "links": {
            "self": f"/api/v1/jobs/{job_id}",
            "list": "/api/v1/jobs",
        },
    }


@router.get(
    "/{job_id}/status",
    summary="Get job status",
    description="Get only the status of a job (lightweight endpoint for polling).",
)
async def get_job_status(
    _api_key: RequireApiKey,
    job_id: str = Path(..., description="Job ID"),
) -> dict[str, Any]:
    """Get job status only (for polling)."""
    queue = get_job_queue()
    job = await queue.get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    return {
        "success": True,
        "data": {
            "id": job.id,
            "status": job.status.value,
            "progress": job.progress,
            "error": job.error,
        },
    }


@router.delete(
    "/{job_id}",
    summary="Cancel job",
    description="Cancel a pending job.",
)
async def cancel_job(
    _api_key: RequireApiKey,
    job_id: str = Path(..., description="Job ID"),
) -> dict[str, Any]:
    """Cancel a pending or running job."""
    queue = get_job_queue()
    job = await queue.get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    if not await queue.cancel_job(job_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel job in {job.status.value} status",
        )

    return {
        "success": True,
        "message": "Job cancelled",
        "data": {"id": job_id, "status": "cancelled"},
    }
