import pytest
from bson import ObjectId
from app.utils.jwt_utils import create_access_token, decode_token
from app.utils.similarity import compute_cosine_similarity
from app.utils.serializers import serialize_mongo_doc
from app.services.recommendation_engine import RecommendationEngine

def test_jwt_generation_and_decoding():
    token = create_access_token({"sub": "user-test-123"})
    assert isinstance(token, str)
    payload = decode_token(token)
    assert payload.get("sub") == "user-test-123"
    assert "exp" in payload

def test_pure_math_cosine_similarity():
    vec_a = {"energy": 0.8, "danceability": 0.7, "acousticness": 0.1}
    vec_b = {"energy": 0.8, "danceability": 0.7, "acousticness": 0.1}
    sim_identical = compute_cosine_similarity(vec_a, vec_b)
    assert round(sim_identical, 4) == 1.0

    vec_c = {"classical": 0.9}
    sim_disjoint = compute_cosine_similarity(vec_a, vec_c)
    assert sim_disjoint == 0.0

def test_serialize_mongo_doc():
    doc = {
        "_id": ObjectId(),
        "playlist_id": "pl-1",
        "nested": {"_id": ObjectId(), "name": "Favorites"},
        "tags": ["rock", "metal"],
    }
    serialized = serialize_mongo_doc(doc)
    assert "_id" not in serialized
    assert serialized["playlist_id"] == "pl-1"
    assert "_id" not in serialized["nested"]
    assert serialized["nested"]["name"] == "Favorites"

def test_recommendation_scoring():
    engine = RecommendationEngine(None, None)
    profile = {
        "user_id": "u1",
        "genre_weights": {"rock": 0.9, "pop": 0.2},
        "top_artists": ["Led Zeppelin"],
        "language_weights": {"en": 0.8},
        "feature_preferences": {"energy": 0.8, "danceability": 0.5, "acousticness": 0.2, "valence": 0.5},
    }
    rock_song = {
        "track_id": "t1",
        "title": "Kashmir",
        "artist": "Led Zeppelin",
        "genre": "rock",
        "language": "en",
        "energy": 0.85,
        "danceability": 0.45,
        "popularity_score": 0.9,
    }
    pop_song = {
        "track_id": "t2",
        "title": "Random Pop",
        "artist": "Unknown Pop Singer",
        "genre": "pop",
        "language": "es",
        "energy": 0.3,
        "popularity_score": 0.3,
    }
    rock_score = engine.score_song(profile, rock_song)
    pop_score = engine.score_song(profile, pop_song)
    assert rock_score > pop_score

def test_recommendation_diversification():
    engine = RecommendationEngine(None, None)
    scored_items = [
        {"track": {"track_id": "1", "artist": "Queen"}, "score": 0.9},
        {"track": {"track_id": "2", "artist": "Queen"}, "score": 0.85},
        {"track": {"track_id": "3", "artist": "Queen"}, "score": 0.80},  # should be excluded (max 2)
        {"track": {"track_id": "4", "artist": "Pink Floyd"}, "score": 0.75},
    ]
    results = engine.diversify_results(scored_items, limit=10)
    queen_tracks = [t for t in results if t["artist"] == "Queen"]
    assert len(queen_tracks) == 2
    assert len(results) == 3

@pytest.mark.anyio
async def test_playlist_creation_and_track_structure():
    from unittest.mock import AsyncMock, MagicMock
    mock_db = MagicMock()
    mock_db.playlists = MagicMock()
    mock_db.playlists.insert_one = AsyncMock()
    mock_db.playlists.find_one = AsyncMock(return_value=None)
    mock_db.playlists.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

    from app.services.playlist_service import PlaylistService
    service = PlaylistService(mock_db)

    # 1. Test create playlist
    created = await service.create_playlist("user-1", "My Lo-Fi Beats")
    assert created["name"] == "My Lo-Fi Beats"
    assert created["user_id"] == "user-1"
    assert "playlist_id" in created
    assert created["track_count"] == 0

    # 2. Test add track with metadata
    meta = {
        "title": "Midnight City",
        "artist": "M83",
        "cover_url": "https://example.com/art.jpg",
        "duration_seconds": 240,
    }
    success = await service.add_track("user-1", created["playlist_id"], "track-xyz", meta=meta)
    assert success is True
    assert mock_db.playlists.update_one.called
