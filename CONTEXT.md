# Project Context — vynl-backend

Core backend service for the VYNL music streaming platform.

---

## 1. Responsibilities

- **Authentication & User Management**: Google OAuth 2.0 with local dev fallback, JWT session issuing (`access_token`, `refresh_token`), CSRF protection, and user taste profiles.
- **Playlist Management**: CRUD endpoints for user playlists, persistent metadata attachment (`title`, `artist`, `cover_url`, `duration_seconds`), duplicate track avoidance, and serialization.
- **Library & Listening History**: User liked tracks, library sync, and play duration tracking.
- **Recommendation Engine**: Dynamic vector scoring with cosine similarity, online profile adaptation, and diversification.

---

## 2. API Endpoints & Contracts

All backend routers are mounted dual-path under both `/v1` and `/api/v1`:

### Playlist Endpoints
| Method | Path | Description |
|---|---|---|
| `GET` | `/v1/playlists/` | Returns `{ "playlists": [...] }` sorted by `updated_at` descending |
| `POST` | `/v1/playlists/` | Body: `{ "name": "...", "description": "..." }`. Returns created playlist |
| `GET` | `/v1/playlists/{playlist_id}` | Returns playlist details enriched with track metadata from audio DB |
| `DELETE` | `/v1/playlists/{playlist_id}` | Deletes playlist |
| `POST` | `/v1/playlists/{playlist_id}/tracks` | Body: `{ "track_id": "...", "title": "...", "artist": "...", "cover_url": "...", "duration_seconds": 120 }` |
| `DELETE` | `/v1/playlists/{playlist_id}/tracks/{track_id}` | Removes track from playlist |

### Auth & User Profile
- `GET /v1/auth/me`: User session verification.
- `GET /v1/auth/google/start`: OAuth initiation.
- `GET /v1/auth/google/callback?code=dev_mock_code`: Development mock login setting session cookies.
- `POST /v1/auth/logout`: Clears session cookies.

### Activity & Recommendations
- `POST /v1/activity/batch`: Telemetry batch ingestion.
- `GET /v1/recommendations/for-you`: Personalized feed.
- `GET /v1/recommendations/radio/{track_id}`: Track seed radio.

---

## 3. Database & Schemas

- **MongoDB Database**: `vynl_backend` (Motor async client)
- **Audio DB Access**: Connected to `vynl_audio` database (`tracks` collection) for cross-service track metadata lookups.
- **Collections**:
  - `users`: User identity records.
  - `user_profiles`: User taste vectors and preferences.
  - `playlists`: `{ playlist_id, user_id, name, description, tracks: [{ track_id, title, artist, cover_url, duration_seconds, added_at }], track_count, created_at, updated_at }`.
  - `library`: User saved tracks.
  - `listening_history`: Historical plays and duration metrics.

---

## 4. Running & Verification

```bash
cd vynl-backend
.\venv\Scripts\python -m uvicorn app.main:app --port 8001 --reload
.\venv\Scripts\python -m pytest -o pythonpath=.
```
