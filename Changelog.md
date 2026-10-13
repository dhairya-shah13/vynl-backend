# Changelog — vynl-backend

All notable changes to the VYNL core backend service are documented in this file in reverse-chronological order.

---

## [2026-10-14 00:25]

### [Category: Dev] — Lyrics Proxy Service & MongoDB TTL Caching
What changed:
- Implemented `GET /v1/lyrics` (and dual-mounted `/api/v1/lyrics`) in `app/api/lyrics.py` requiring authentication via `get_current_user`.
- Built `LyricsService` (`app/services/lyrics_service.py`) querying LRCLIB API (`GET /get` with `GET /search` fallback and duration scoring), title noise stripping, and Latin-script language filtering (>15% non-Latin rejected).
- Integrated MongoDB `lyrics_cache` in `vynl_backend` with TTL expiration indexes (7 days for hits, 1 day for misses) and unique `cache_key` indexing in `app/db/mongo.py`.
- Created comprehensive test suite in `tests/test_lyrics.py` covering synced lyrics, plain-only lyrics, 404 search fallback, timeout resilience, cache hit/miss TTL, instrumental flag, and non-Latin script rejection (16/16 tests passing).

Why:
- Provides a high-performance proxy for synchronized and plain lyrics with automatic database caching and Latin-script filtering, protecting third-party rate limits and delivering instant responses to client requests.

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
