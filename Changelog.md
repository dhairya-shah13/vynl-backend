# Changelog — vynl-backend

All notable changes to the VYNL core backend service are documented in this file in reverse-chronological order.

---

## [2026-10-14 00:05]

### [Category: Dev] — Context & Documentation Update
What changed:
- Updated `CONTEXT.md` with complete playlist endpoints, metadata enrichment schema, and MongoDB collections structure.
Why:
- Ensure standalone documentation integrity within the backend repository per repository standards.

---

## [2026-10-13 23:59]

### [Category: Dev] — Playlist Track Metadata Support & Duplicate Handling
What changed:
- Updated `AddTrackRequest` schema in `app/api/playlists.py` to accept optional track metadata (`title`, `artist`, `cover_url`, `duration_seconds`).
- Enhanced `PlaylistService.add_track` in `app/services/playlist_service.py` to persist metadata directly into the playlist tracks array and guard against duplicate track insertion.
- Enhanced `PlaylistService.get_playlist` to preserve stored metadata if `audio_db` tracks are not yet indexed, ensuring playlists never render "Unknown Title" or empty covers.
- Added comprehensive unit test suite in `tests/test_backend.py` covering playlist creation, track entry structure, and metadata persistence.
- Verified all 6 unit tests pass via `pytest`.

Why:
- Allows the frontend to pass rich track metadata when adding songs from search results and protects against duplicate entries.
