"""
Announcement endpoints for the High School Management System API
"""

from datetime import date
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementPayload(BaseModel):
    message: str = Field(..., min_length=5, max_length=500)
    expires_on: str
    starts_on: Optional[str] = None


def _parse_iso_date(date_value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(date_value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must be a valid date in YYYY-MM-DD format"
        ) from exc


def _require_authenticated_teacher(teacher_username: Optional[str]) -> Dict[str, Any]:
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required for this action")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def _normalize_announcement(announcement: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(announcement["_id"]),
        "message": announcement["message"],
        "starts_on": announcement.get("starts_on"),
        "expires_on": announcement["expires_on"]
    }


@router.get("", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get active announcements that should be visible to all users."""
    today = date.today().isoformat()

    query = {
        "expires_on": {"$gte": today},
        "$or": [
            {"starts_on": None},
            {"starts_on": {"$exists": False}},
            {"starts_on": {"$lte": today}}
        ]
    }

    announcements = []
    for item in announcements_collection.find(query).sort("expires_on", 1):
        announcements.append(_normalize_announcement(item))

    return announcements


@router.get("/all", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Get all announcements, including future and expired, for authenticated users."""
    _require_authenticated_teacher(teacher_username)

    announcements = []
    for item in announcements_collection.find({}).sort([("expires_on", 1), ("_id", 1)]):
        announcements.append(_normalize_announcement(item))

    return announcements


@router.post("", response_model=Dict[str, str])
def create_announcement(payload: AnnouncementPayload, teacher_username: Optional[str] = Query(None)) -> Dict[str, str]:
    """Create a new announcement (authenticated users only)."""
    _require_authenticated_teacher(teacher_username)

    expires_on = _parse_iso_date(payload.expires_on, "expires_on")
    starts_on = None

    if payload.starts_on:
        starts_on = _parse_iso_date(payload.starts_on, "starts_on")
        if starts_on > expires_on:
            raise HTTPException(status_code=400, detail="starts_on cannot be later than expires_on")

    message = payload.message.strip()
    if len(message) < 5:
        raise HTTPException(status_code=400, detail="message must be at least 5 characters")

    announcement_id = f"announcement-{uuid4().hex[:12]}"
    announcements_collection.insert_one(
        {
            "_id": announcement_id,
            "message": message,
            "starts_on": starts_on.isoformat() if starts_on else None,
            "expires_on": expires_on.isoformat()
        }
    )

    return {"id": announcement_id, "message": "Announcement created"}


@router.put("/{announcement_id}", response_model=Dict[str, str])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    """Update an existing announcement (authenticated users only)."""
    _require_authenticated_teacher(teacher_username)

    expires_on = _parse_iso_date(payload.expires_on, "expires_on")
    starts_on = None

    if payload.starts_on:
        starts_on = _parse_iso_date(payload.starts_on, "starts_on")
        if starts_on > expires_on:
            raise HTTPException(status_code=400, detail="starts_on cannot be later than expires_on")

    update_result = announcements_collection.update_one(
        {"_id": announcement_id},
        {
            "$set": {
                "message": payload.message.strip(),
                "starts_on": starts_on.isoformat() if starts_on else None,
                "expires_on": expires_on.isoformat()
            }
        }
    )

    if update_result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement updated"}


@router.delete("/{announcement_id}", response_model=Dict[str, str])
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    """Delete an announcement (authenticated users only)."""
    _require_authenticated_teacher(teacher_username)

    delete_result = announcements_collection.delete_one({"_id": announcement_id})
    if delete_result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
