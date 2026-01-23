"""Session endpoints - Cookie management for browser extension."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from shopee_scraper.api.dependencies import RequireApiKey
from shopee_scraper.utils.logging import get_logger


logger = get_logger(__name__)

router = APIRouter(prefix="/session", tags=["Session"])


# =============================================================================
# Schemas
# =============================================================================


class CookieUploadRequest(BaseModel):
    """Request body for cookie upload."""

    cookies: list[dict[str, Any]] = Field(..., min_length=1)


class CookieUploadResponse(BaseModel):
    """Response for cookie upload."""

    success: bool = True
    message: str
    data: dict[str, Any]


class CookieStatusResponse(BaseModel):
    """Response for cookie status check."""

    success: bool = True
    data: dict[str, Any]


# =============================================================================
# Helper Functions
# =============================================================================


def get_session_dir() -> Path:
    """Get session directory path."""
    session_dir = Path("./data/sessions")
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def get_uploaded_cookies_path() -> Path:
    """Get path for uploaded cookies file."""
    return get_session_dir() / "uploaded_cookies.json"


# =============================================================================
# Endpoints
# =============================================================================


@router.post(
    "/cookie-upload",
    response_model=CookieUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload cookies from browser extension",
    description="Receive and store cookies uploaded from the browser extension.",
)
async def upload_cookies(
    request: CookieUploadRequest,
    _api_key: RequireApiKey,
) -> CookieUploadResponse:
    """
    Upload cookies from browser extension.

    The browser extension sends Shopee cookies after user logs in manually.
    These cookies are stored and used for subsequent scraping operations.
    """
    try:
        cookies = request.cookies

        if not cookies:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No cookies provided",
            )

        # Filter only Shopee cookies
        shopee_cookies = [
            c
            for c in cookies
            if ".shopee.co.id" in c.get("domain", "")
            or "shopee.co.id" in c.get("domain", "")
        ]

        if not shopee_cookies:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No Shopee cookies found in the provided data",
            )

        # Save cookies with metadata
        from datetime import timedelta

        uploaded_at = datetime.now()
        expires_at = uploaded_at + timedelta(days=7)

        data = {
            "cookies": shopee_cookies,
            "uploaded_at": uploaded_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "source": "browser_extension",
        }

        # Save to file
        cookies_path = get_uploaded_cookies_path()
        with cookies_path.open("w") as f:
            json.dump(data, f, indent=2)

        logger.info(
            "Cookies uploaded successfully",
            count=len(shopee_cookies),
            path=str(cookies_path),
        )

        return CookieUploadResponse(
            success=True,
            message="Cookies uploaded successfully",
            data={
                "cookies_count": len(shopee_cookies),
                "uploaded_at": uploaded_at.isoformat(),
                "expires_at": expires_at.isoformat(),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to upload cookies", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload cookies: {e!s}",
        ) from e


@router.get(
    "/cookie-status",
    response_model=CookieStatusResponse,
    summary="Check cookie status",
    description="Check if uploaded cookies exist and are still valid.",
)
async def get_cookie_status(
    _api_key: RequireApiKey,
) -> CookieStatusResponse:
    """
    Check cookie status.

    Returns information about:
    - Whether cookies exist
    - Whether they are still valid (not expired)
    - Expiration date and days remaining
    """
    cookies_path = get_uploaded_cookies_path()

    # Check if file exists
    if not cookies_path.exists():
        return CookieStatusResponse(
            success=True,
            data={
                "has_session": False,
                "valid": False,
                "message": "No cookies found. Please upload via browser extension.",
            },
        )

    try:
        with cookies_path.open() as f:
            data = json.load(f)

        uploaded_at_str = data.get("uploaded_at")
        expires_at_str = data.get("expires_at")
        cookies = data.get("cookies", [])

        if not expires_at_str:
            return CookieStatusResponse(
                success=True,
                data={
                    "has_session": True,
                    "valid": False,
                    "message": "Invalid cookie file format",
                },
            )

        uploaded_at = (
            datetime.fromisoformat(uploaded_at_str) if uploaded_at_str else None
        )
        expires_at = datetime.fromisoformat(expires_at_str)
        now = datetime.now()

        # Check if expired
        is_valid = now < expires_at
        days_remaining = (expires_at - now).days if is_valid else 0

        if is_valid:
            return CookieStatusResponse(
                success=True,
                data={
                    "has_session": True,
                    "valid": True,
                    "cookies_count": len(cookies),
                    "uploaded_at": uploaded_at.isoformat() if uploaded_at else None,
                    "expires_at": expires_at.isoformat(),
                    "days_remaining": days_remaining,
                },
            )
        else:
            return CookieStatusResponse(
                success=True,
                data={
                    "has_session": True,
                    "valid": False,
                    "uploaded_at": uploaded_at.isoformat() if uploaded_at else None,
                    "expired_at": expires_at.isoformat(),
                    "message": "Session expired. Please re-login and upload new cookies.",
                },
            )

    except json.JSONDecodeError:
        logger.error("Invalid cookie file format")
        return CookieStatusResponse(
            success=True,
            data={
                "has_session": False,
                "valid": False,
                "message": "Invalid cookie file. Please re-upload.",
            },
        )
    except Exception as e:
        logger.error("Failed to check cookie status", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check cookie status: {e!s}",
        ) from e
