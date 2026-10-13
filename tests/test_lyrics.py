import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
from app.services.lyrics_service import (
    LyricsService,
    clean_track_title,
    is_english_latin_lyrics,
    parse_lrc_lines,
    normalize_cache_key,
)

def test_clean_track_title():
    assert clean_track_title("Midnight City (feat. Vocals)") == "Midnight City"
    assert clean_track_title("Starman - Remastered 2012") == "Starman"
    assert clean_track_title("Rolling in the Deep (Official Video)") == "Rolling in the Deep"
    assert clean_track_title("Something [ft. Artist] (Lyric Video)") == "Something"
    assert clean_track_title("Simple Song") == "Simple Song"
    # Artist suffix in title string
    assert clean_track_title("Die For You - The Weeknd -", "The Weeknd") == "Die For You"
    assert clean_track_title("luther - Kendrick Lamar -", "Kendrick Lamar") == "luther"
    assert clean_track_title("Thunderstruck - ACDC -", "ACDC") == "Thunderstruck"

def test_is_english_latin_lyrics():
    # Pure English
    assert is_english_latin_lyrics("Hello darkness my old friend, I've come to talk with you again") is True
    # Accented Latin characters (e.g., French, Spanish)
    assert is_english_latin_lyrics("C'est la vie, où est la bibliothèque, señor") is True
    # Non-Latin: Hindi / Devanagari (>15%)
    assert is_english_latin_lyrics("तू ही मेरी मंज़िल है, पहचान मेरी तू") is False
    # Non-Latin: Gujarati
    assert is_english_latin_lyrics("મારું મન મોહી ગયું રે પિયુ") is False
    # Non-Latin: CJK
    assert is_english_latin_lyrics("你好世界 今天的雨很大") is False
    # Mostly English with one tiny non-latin symbol (<15%)
    assert is_english_latin_lyrics("Dancing through the night with you forever and ever and always") is True

def test_parse_lrc_lines():
    lrc = """
    [ti:Test Title]
    [ar:Test Artist]
    [offset:500]
    [00:10.50]Line one text
    [01:05.120]Line two text
    [01:20.00][01:25.00]Repeated chorus
    """
    lines = parse_lrc_lines(lrc)
    assert len(lines) == 4
    # Offset of 500ms adds 0.5s to lines
    assert lines[0]["text"] == "Line one text"
    assert lines[0]["time"] == 11.0  # 10.50 + 0.5
    assert lines[1]["text"] == "Line two text"
    assert lines[1]["time"] == 65.62 # 65.12 + 0.5
    assert lines[2]["text"] == "Repeated chorus"
    assert lines[2]["time"] == 80.5  # 80.0 + 0.5
    assert lines[3]["text"] == "Repeated chorus"
    assert lines[3]["time"] == 85.5  # 85.0 + 0.5

@pytest.mark.anyio
async def test_lyrics_synced_hit():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": 123,
        "instrumental": False,
        "syncedLyrics": "[00:05.00]First line\n[00:12.50]Second line",
        "plainLyrics": "First line\nSecond line",
    }
    mock_client.get = AsyncMock(return_value=mock_resp)

    service = LyricsService(db=None, http_client=mock_client)
    res = await service.get_lyrics("Midnight City", "M83", duration=240)
    assert res["status"] == "synced"
    assert len(res["synced_lines"]) == 2
    assert res["synced_lines"][0]["text"] == "First line"
    assert res["synced_lines"][0]["time"] == 5.0

@pytest.mark.anyio
async def test_lyrics_plain_only_hit():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": 124,
        "instrumental": False,
        "syncedLyrics": None,
        "plainLyrics": "Line one\nLine two\nLine three",
    }
    mock_client.get = AsyncMock(return_value=mock_resp)

    service = LyricsService(db=None, http_client=mock_client)
    res = await service.get_lyrics("Acoustic Melody", "Indie Band", duration=180)
    assert res["status"] == "plain"
    assert len(res["synced_lines"]) == 0
    assert len(res["plain_lines"]) == 3
    assert res["plain_lines"][0] == "Line one"

@pytest.mark.anyio
async def test_lyrics_404_search_fallback():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    # First call returns 404, second call returns search list
    resp_404 = MagicMock(status_code=404)
    resp_search = MagicMock(status_code=200)
    resp_search.json.return_value = [
        {
            "id": 999,
            "name": "Different Song",
            "artistName": "Other",
            "duration": 50,
            "syncedLyrics": None,
        },
        {
            "id": 1000,
            "trackName": "Midnight City",
            "artistName": "M83",
            "duration": 241,
            "instrumental": False,
            "syncedLyrics": "[00:10.00]Found via search",
            "plainLyrics": "Found via search",
        },
    ]

    mock_client.get = AsyncMock(side_effect=[resp_404, resp_search])

    service = LyricsService(db=None, http_client=mock_client)
    res = await service.get_lyrics("Midnight City (Remaster)", "M83", duration=240)
    assert res["status"] == "synced"
    assert len(res["synced_lines"]) == 1
    assert res["synced_lines"][0]["text"] == "Found via search"

@pytest.mark.anyio
async def test_lyrics_timeout_and_error_handling():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("Connection timed out"))

    service = LyricsService(db=None, http_client=mock_client)
    res = await service.get_lyrics("Timeout Track", "Unknown", duration=120)
    assert res["status"] == "none"
    assert res["synced_lines"] == []
    assert res["plain_lines"] == []

@pytest.mark.anyio
async def test_lyrics_cache_hit_and_miss_ttl():
    mock_db = MagicMock()
    mock_db.lyrics_cache = MagicMock()
    
    # 1. Existing cache hit
    cached_doc = {
        "cache_key": "song|artist|120",
        "status": "synced",
        "synced_lines": [{"time": 1.0, "text": "Cached line"}],
        "plain_lines": ["Cached line"],
        "is_instrumental": False,
    }
    mock_db.lyrics_cache.find_one = AsyncMock(return_value=cached_doc)
    mock_db.lyrics_cache.update_one = AsyncMock()

    service = LyricsService(db=mock_db, http_client=None)
    res = await service.get_lyrics("Song", "Artist", duration=120)
    assert res["status"] == "synced"
    assert res["synced_lines"][0]["text"] == "Cached line"
    assert not mock_db.lyrics_cache.update_one.called

    # 2. Cache miss -> stores with TTL
    mock_db.lyrics_cache.find_one = AsyncMock(return_value=None)
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = MagicMock(status_code=404)
    mock_client.get = AsyncMock(return_value=mock_resp)

    service2 = LyricsService(db=mock_db, http_client=mock_client)
    res2 = await service2.get_lyrics("Nonexistent", "Ghost", duration=90)
    assert res2["status"] == "none"
    assert mock_db.lyrics_cache.update_one.called
    upsert_args = mock_db.lyrics_cache.update_one.call_args[0]
    set_doc = upsert_args[1]["$set"]
    assert set_doc["status"] == "none"
    # Miss TTL is 1 day
    delta = set_doc["expire_at"] - set_doc["created_at"]
    assert delta.days == 1

@pytest.mark.anyio
async def test_lyrics_non_english_rejected():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": 555,
        "instrumental": False,
        "syncedLyrics": "[00:02.00]તુજ વિના મને ચેન ના પડે\n[00:10.00]મારું દિલ તું",
        "plainLyrics": "તુજ વિના મને ચેન ના પડે\nમારું દિલ તું",
    }
    mock_client.get = AsyncMock(return_value=mock_resp)

    service = LyricsService(db=None, http_client=mock_client)
    res = await service.get_lyrics("Gujarati Song", "Folk Artist", duration=200)
    assert res["status"] == "none"
    assert res["synced_lines"] == []
    assert res["plain_lines"] == []

@pytest.mark.anyio
async def test_lyrics_instrumental_flag():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": 777,
        "instrumental": True,
        "syncedLyrics": None,
        "plainLyrics": None,
    }
    mock_client.get = AsyncMock(return_value=mock_resp)

    service = LyricsService(db=None, http_client=mock_client)
    res = await service.get_lyrics("Orchestra Prelude", "Classical Symphony", duration=300)
    assert res["status"] == "none"
    assert res["is_instrumental"] is True
