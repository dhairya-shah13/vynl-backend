from fastapi import APIRouter, Depends, Query, Request
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from app.dependencies import get_current_user, get_db
from app.services.lyrics_service import LyricsService

router = APIRouter(prefix="/lyrics", tags=["lyrics"])

async def get_current_user_or_guest(request: Request) -> str:
    """Extract authenticated user session if present; allow guest browsing without auth exception."""
    try:
        return await get_current_user(request)
    except Exception:
        return "guest"

class SyncedLine(BaseModel):
    time: float
    text: str

class LyricsResponse(BaseModel):
    status: str  # "synced" | "plain" | "none"
    synced_lines: List[SyncedLine] = []
    plain_lines: List[str] = []
    is_instrumental: bool = False

@router.get("", response_model=LyricsResponse)
@router.get("/", response_model=LyricsResponse)
async def get_lyrics(
    title: Optional[str] = Query(None, description="Track title"),
    artist: Optional[str] = Query(None, description="Artist name"),
    album: Optional[str] = Query(None, description="Album name"),
    duration: Optional[float] = Query(None, description="Track duration in seconds"),
    track_id: Optional[str] = Query(None, description="Optional track ID for lookup"),
    user_id: str = Depends(get_current_user_or_guest),
    db=Depends(get_db),
):
    """
    Fetch synchronized or plain lyrics from LRCLIB with database TTL caching.
    Requires user authentication like all other /v1 endpoints.
    """
    service = LyricsService(db)
    result = await service.get_lyrics(
        title=title or "",
        artist=artist or "",
        album=album,
        duration=duration,
    )
    return result
