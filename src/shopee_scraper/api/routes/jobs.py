"""Job endpoints - RESTful resource for job management."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query, Response, status

from shopee_scraper.api.dependencies import RequireApiKey
from shopee_scraper.api.jobs import JobStatus, get_job_queue
from shopee_scraper.utils.logging import get_logger


logger = get_logger(__name__)

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
    "/{job_id}/download",
    summary="Download job results",
    description="Download completed job results as a JSON file.",
)
async def download_job_result(
    _api_key: RequireApiKey,
    job_id: str = Path(..., description="Job ID"),
) -> Response:
    """Download completed job results as a JSON file."""
    queue = get_job_queue()
    job = await queue.get_job(job_id)

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job not completed (status: {job.status.value})",
        )

    if not job.result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job has no results",
        )

    filename = f"shopee-{job.type}-{job.id[:8]}.json"
    content = json.dumps(job.result, ensure_ascii=False, indent=2)

    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
            "download": f"/api/v1/jobs/{job_id}/download",
            "list": "/api/v1/jobs",
        },
    }


@router.get(
    "/{job_id}/status",
    summary="Get job status (DEPRECATED)",
    description="""
**DEPRECATED**: This polling endpoint is deprecated and will be removed in v1.0.0.

Use WebSocket endpoint instead for real-time updates:
`ws://host/api/v1/ws/jobs/{job_id}`

This endpoint returns only the status of a job. For real-time status updates,
connect to the WebSocket endpoint which provides push notifications for:
- Status changes (pending → running → completed/failed)
- Progress updates
- Completion with results

**Migration Guide:**
```javascript
// OLD (polling - deprecated)
setInterval(async () => {
    const res = await fetch('/api/v1/jobs/{job_id}/status');
    const data = await res.json();
}, 2000);

// NEW (WebSocket - recommended)
const ws = new WebSocket('ws://host/api/v1/ws/jobs/{job_id}');
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```
""",
    deprecated=True,
    responses={
        200: {
            "description": "Job status",
            "headers": {
                "Deprecation": {
                    "description": "Deprecation notice",
                    "schema": {"type": "string"},
                },
                "Sunset": {
                    "description": "Date when endpoint will be removed",
                    "schema": {"type": "string"},
                },
                "Link": {
                    "description": "Link to replacement endpoint",
                    "schema": {"type": "string"},
                },
            },
        },
    },
)
async def get_job_status(
    response: Response,
    _api_key: RequireApiKey,
    job_id: str = Path(..., description="Job ID"),
) -> dict[str, Any]:
    """
    Get job status only (for polling).

    DEPRECATED: Use WebSocket endpoint /api/v1/ws/jobs/{job_id} instead.
    """
    # Log deprecation warning
    logger.warning(
        "Deprecated endpoint called: GET /jobs/{job_id}/status",
        job_id=job_id,
        alternative="WebSocket /api/v1/ws/jobs/{job_id}",
    )

    # Add deprecation headers (RFC 8594)
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "2025-12-31T23:59:59Z"
    response.headers["Link"] = f'</api/v1/ws/jobs/{job_id}>; rel="successor-version"'

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
        "_deprecation": {
            "message": "This endpoint is deprecated. Use WebSocket for real-time updates.",
            "alternative": f"ws://{{host}}/api/v1/ws/jobs/{job_id}",
            "sunset": "2025-12-31",
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
