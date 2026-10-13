import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from app.utils.serializers import serialize_mongo_doc

from app.db.mongo import get_audio_db

class PlaylistService:
    def __init__(self, db):
        self.db = db
        self.audio_db = get_audio_db()

    async def get_playlists(self, user_id: str) -> List[Dict[str, Any]]:
        if self.db is None:
            return []
        cursor = self.db.playlists.find({"user_id": user_id}).sort("updated_at", -1)
        docs = await cursor.to_list(length=100)
        return serialize_mongo_doc(docs)

    async def get_playlist(self, user_id: str, playlist_id: str) -> Optional[Dict[str, Any]]:
        if self.db is None:
            return None
        doc = await self.db.playlists.find_one({
            "user_id": user_id,
            "playlist_id": playlist_id,
        })
        if not doc:
            return None
        tracks = doc.get("tracks", [])
        if self.audio_db is not None and tracks:
            track_ids = [t["track_id"] for t in tracks if "track_id" in t]
            track_docs = await self.audio_db.tracks.find({"track_id": {"$in": track_ids}}).to_list(length=len(track_ids))
            track_map = {t["track_id"]: t for t in track_docs}
            for t in tracks:
                meta = track_map.get(t.get("track_id"))
                if meta:
                    t["title"] = meta.get("title") or t.get("title") or "Unknown Title"
                    t["artist"] = meta.get("artist") or t.get("artist") or "Unknown Artist"
                    t["album"] = meta.get("album") or t.get("album") or ""
                    t["cover_url"] = meta.get("cover_url") or meta.get("artwork_url") or t.get("cover_url") or ""
                    t["duration_seconds"] = meta.get("duration_seconds") or t.get("duration_seconds") or 0
        for t in tracks:
            t.setdefault("title", "Unknown Title")
            t.setdefault("artist", "Unknown Artist")
            t.setdefault("album", "")
            t.setdefault("cover_url", "")
            t.setdefault("duration_seconds", 0)
        return serialize_mongo_doc(doc)

    async def create_playlist(self, user_id: str, name: str, description: str = "") -> Dict[str, Any]:
        playlist_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        doc = {
            "playlist_id": playlist_id,
            "user_id": user_id,
            "name": name.strip(),
            "description": description.strip(),
            "tracks": [],
            "track_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        if self.db is not None:
            await self.db.playlists.insert_one(doc)
        return serialize_mongo_doc(doc)

    async def delete_playlist(self, user_id: str, playlist_id: str) -> bool:
        if self.db is None:
            return False
        res = await self.db.playlists.delete_one({"user_id": user_id, "playlist_id": playlist_id})
        return res.deleted_count > 0

    async def add_track(self, user_id: str, playlist_id: str, track_id: str, meta: Optional[Dict[str, Any]] = None) -> bool:
        if self.db is None:
            return False

        # Idempotent: avoid duplicate tracks in the same playlist
        existing = await self.db.playlists.find_one({
            "user_id": user_id,
            "playlist_id": playlist_id,
            "tracks.track_id": track_id,
        })
        if existing:
            return True

        now = datetime.now(timezone.utc)
        track_entry = {
            "track_id": track_id,
            "added_at": now,
        }
        if meta:
            if meta.get("title"):
                track_entry["title"] = meta["title"]
            if meta.get("artist"):
                track_entry["artist"] = meta["artist"]
            if meta.get("cover_url"):
                track_entry["cover_url"] = meta["cover_url"]
            if meta.get("duration_seconds") is not None:
                track_entry["duration_seconds"] = meta["duration_seconds"]

        res = await self.db.playlists.update_one(
            {"user_id": user_id, "playlist_id": playlist_id},
            {
                "$push": {"tracks": track_entry},
                "$inc": {"track_count": 1},
                "$set": {"updated_at": now},
            }
        )
        return res.modified_count > 0

    async def remove_track(self, user_id: str, playlist_id: str, track_id: str) -> bool:
        if self.db is None:
            return False
        now = datetime.now(timezone.utc)
        res = await self.db.playlists.update_one(
            {"user_id": user_id, "playlist_id": playlist_id},
            {
                "$pull": {"tracks": {"track_id": track_id}},
                "$inc": {"track_count": -1},
                "$set": {"updated_at": now},
            }
        )
        return res.modified_count > 0
