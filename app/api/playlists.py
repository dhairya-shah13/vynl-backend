from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from app.dependencies import get_current_user, get_db
from app.services.playlist_service import PlaylistService

router = APIRouter(prefix="/playlists", tags=["playlists"])

class CreatePlaylistRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = ""

class AddTrackRequest(BaseModel):
    track_id: str
    title: Optional[str] = None
    artist: Optional[str] = None
    cover_url: Optional[str] = None
    duration_seconds: Optional[int] = None

@router.get("/")
async def get_user_playlists(user_id: str = Depends(get_current_user), db=Depends(get_db)):
    service = PlaylistService(db)
    playlists = await service.get_playlists(user_id)
    return {"playlists": playlists}

@router.post("/")
async def create_new_playlist(req: CreatePlaylistRequest, user_id: str = Depends(get_current_user), db=Depends(get_db)):
    service = PlaylistService(db)
    created = await service.create_playlist(user_id, req.name, req.description or "")
    return created

@router.get("/{playlist_id}")
async def get_playlist_details(playlist_id: str, user_id: str = Depends(get_current_user), db=Depends(get_db)):
    service = PlaylistService(db)
    playlist = await service.get_playlist(user_id, playlist_id)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return playlist

@router.delete("/{playlist_id}")
async def delete_playlist_by_id(playlist_id: str, user_id: str = Depends(get_current_user), db=Depends(get_db)):
    service = PlaylistService(db)
    deleted = await service.delete_playlist(user_id, playlist_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return {"status": "deleted"}

@router.post("/{playlist_id}/tracks")
async def add_track_to_playlist(
    playlist_id: str,
    req: AddTrackRequest,
    user_id: str = Depends(get_current_user),
    db=Depends(get_db)
):
    service = PlaylistService(db)
    meta = {
        "title": req.title,
        "artist": req.artist,
        "cover_url": req.cover_url,
        "duration_seconds": req.duration_seconds,
    }
    added = await service.add_track(user_id, playlist_id, req.track_id, meta=meta)
    if not added:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return {"status": "added", "track_id": req.track_id}

@router.delete("/{playlist_id}/tracks/{track_id}")
async def remove_track_from_playlist(
    playlist_id: str,
    track_id: str,
    user_id: str = Depends(get_current_user),
    db=Depends(get_db)
):
    service = PlaylistService(db)
    removed = await service.remove_track(user_id, playlist_id, track_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Track or playlist not found")
    return {"status": "removed", "track_id": track_id}
