import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
import httpx

logger = logging.getLogger(__name__)

LRCLIB_BASE_URL = "https://lrclib.net/api"
USER_AGENT = "VYNL/1.0"
REQUEST_TIMEOUT = 5.0

# Latin script regex covering Basic Latin, Latin-1 Supplement, Latin Extended A/B, Latin Extended Additional
LATIN_REGEX = re.compile(r"^[a-zA-Z\u00C0-\u024F\u1E00-\u1EFF]$")

def clean_track_title(title: str, artist: str = "") -> str:
    """Strip noise from titles such as (feat. ...), [Official Video], - Remastered, and - Artist - suffix."""
    if not title:
        return ""
    cleaned = title
    # Remove (feat. ...), [feat. ...], (ft. ...), [ft. ...]
    cleaned = re.sub(r"[\(\[](?:feat|ft)\.?\s+[^\)\]]+[\)\]]", "", cleaned, flags=re.IGNORECASE)
    # Remove (Official Video), [Official Music Video], (Audio), (Lyric Video), etc.
    cleaned = re.sub(
        r"[\(\[](?:official\s+(?:video|audio|music\s+video|lyric\s+video)|audio|lyric\s+video|lyrics)[\)\]]",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # If artist is given, remove any trailing or embedded " - <artist> -" or " - <artist>"
    if artist:
        cleaned = re.sub(rf"-\s*{re.escape(artist.strip())}\s*-?", "", cleaned, flags=re.IGNORECASE)
    # Also strip general trailing artist pattern: "- <name> -"
    cleaned = re.sub(r"-\s*[^-]+-\s*$", "", cleaned)
    # Remove - Remastered..., - Live..., etc.
    cleaned = re.sub(
        r"-\s*(?:remastered|live|mono|stereo|deluxe|bonus\s+track|anniversary|edit|radio\s+edit).*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Trim lingering hyphens, brackets, whitespace
    cleaned = re.sub(r"^\s*[-–—\s]+|\s*[-–—\s]+$", "", cleaned)
    cleaned = " ".join(cleaned.split())
    return cleaned or title

def is_english_latin_lyrics(text: str) -> bool:
    """
    Check if text is predominantly Latin script.
    If more than ~15% of alphabetical characters are non-Latin, return False.
    """
    if not text:
        return False
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    non_latin = [ch for ch in letters if not LATIN_REGEX.match(ch)]
    ratio = len(non_latin) / len(letters)
    return ratio <= 0.15

def parse_lrc_lines(lrc_text: str) -> List[Dict[str, Any]]:
    """Parse LRC content into sorted list of { "time": float, "text": str }."""
    if not lrc_text:
        return []

    offset_ms = 0.0
    offset_match = re.search(r"\[offset:\s*([+-]?\d+)\]", lrc_text, flags=re.IGNORECASE)
    if offset_match:
        try:
            offset_ms = float(offset_match.group(1))
        except ValueError:
            offset_ms = 0.0

    lines: List[Dict[str, Any]] = []
    timestamp_pattern = re.compile(r"\[(\d{1,2}):(\d{2})(?:\.(\d{2,3}))?\]")

    for raw_line in lrc_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Ignore ID metadata tags like [ar: ...], [ti: ...], etc.
        if re.match(r"^\[[a-zA-Z]{2,8}:", line):
            continue

        timestamps = list(timestamp_pattern.finditer(line))
        if not timestamps:
            continue

        lyric_text = timestamp_pattern.sub("", line).strip()
        if not lyric_text:
            continue

        for match in timestamps:
            mins = int(match.group(1))
            secs = int(match.group(2))
            millis_part = match.group(3) or "0"
            millis = float(millis_part) / (1000 if len(millis_part) == 3 else 100)
            time_sec = round(mins * 60 + secs + millis + (offset_ms / 1000.0), 2)
            if time_sec < 0:
                time_sec = 0.0
            lines.append({"time": time_sec, "text": lyric_text})

    lines.sort(key=lambda x: x["time"])
    return lines

def normalize_cache_key(title: str, artist: str, duration: Optional[float]) -> str:
    clean_t = clean_track_title(title or "", artist or "").lower().strip()
    clean_a = (artist or "").lower().strip()
    dur_int = int(round(float(duration))) if duration else 0
    return f"{clean_t}|{clean_a}|{dur_int}"

class LyricsService:
    def __init__(self, db=None, http_client: Optional[httpx.AsyncClient] = None):
        self.db = db
        self.http_client = http_client

    async def get_lyrics(
        self,
        title: str,
        artist: str,
        album: Optional[str] = None,
        duration: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Fetch lyrics with cache-first strategy.
        Falls back to search if exact match 404s.
        Enforces Latin-script language rule and returns normalized structure.
        """
        artist_name = (artist or "").strip()
        clean_title = clean_track_title(title or "", artist_name)
        dur_val = float(duration) if duration else 0.0
        cache_key = normalize_cache_key(clean_title, artist_name, dur_val)

        # 1. Check MongoDB cache if database is available
        if self.db is not None:
            try:
                cached = await self.db.lyrics_cache.find_one({"cache_key": cache_key})
                if cached:
                    return {
                        "status": cached.get("status", "none"),
                        "synced_lines": cached.get("synced_lines", []),
                        "plain_lines": cached.get("plain_lines", []),
                        "is_instrumental": cached.get("is_instrumental", False),
                    }
            except Exception as e:
                logger.warning("Error reading from lyrics_cache: %s", e)

        # 2. Query LRCLIB
        result_data = await self._fetch_from_lrclib(clean_title, artist_name, album, dur_val)

        # 3. Cache result in MongoDB
        if self.db is not None:
            try:
                now = datetime.now(timezone.utc)
                ttl_days = 7 if result_data.get("status") in ("synced", "plain") else 1
                expire_at = now + timedelta(days=ttl_days)

                doc = {
                    "cache_key": cache_key,
                    "title": clean_title,
                    "artist": artist_name,
                    "duration": dur_val,
                    "status": result_data.get("status", "none"),
                    "synced_lines": result_data.get("synced_lines", []),
                    "plain_lines": result_data.get("plain_lines", []),
                    "is_instrumental": result_data.get("is_instrumental", False),
                    "created_at": now,
                    "expire_at": expire_at,
                }
                await self.db.lyrics_cache.update_one(
                    {"cache_key": cache_key},
                    {"$set": doc},
                    upsert=True,
                )
            except Exception as e:
                logger.warning("Error caching lyrics result: %s", e)

        return result_data

    async def _fetch_from_lrclib(
        self,
        title: str,
        artist: str,
        album: Optional[str],
        duration: float,
    ) -> Dict[str, Any]:
        headers = {"User-Agent": USER_AGENT}
        client = self.http_client or httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
        should_close = self.http_client is None

        try:
            # Step A: Primary GET /get
            params = {
                "track_name": title,
                "artist_name": artist,
            }
            if album:
                params["album_name"] = album
            if duration > 0:
                params["duration"] = int(round(duration))

            resp = None
            try:
                resp = await client.get(
                    f"{LRCLIB_BASE_URL}/get",
                    params=params,
                    headers=headers,
                )
            except (httpx.TimeoutException, httpx.RequestError) as err:
                logger.warning("LRCLIB /get request failed: %s", err)

            data = None
            if resp is not None and resp.status_code == 200:
                data = resp.json()
            elif resp is not None and resp.status_code == 404:
                # Step B: Fallback GET /search
                search_params = {
                    "track_name": title,
                    "artist_name": artist,
                }
                try:
                    search_resp = await client.get(
                        f"{LRCLIB_BASE_URL}/search",
                        params=search_params,
                        headers=headers,
                    )
                    if search_resp.status_code == 200:
                        candidates = search_resp.json()
                        data = self._pick_best_candidate(candidates, title, artist, duration)
                except (httpx.TimeoutException, httpx.RequestError) as err:
                    logger.warning("LRCLIB /search fallback failed: %s", err)

            if not data:
                return {
                    "status": "none",
                    "synced_lines": [],
                    "plain_lines": [],
                    "is_instrumental": False,
                }

            # Handle instrumental tracks
            if data.get("instrumental") is True:
                return {
                    "status": "none",
                    "synced_lines": [],
                    "plain_lines": [],
                    "is_instrumental": True,
                }

            synced_lrc = data.get("syncedLyrics") or ""
            plain_text = data.get("plainLyrics") or ""

            # Check Latin script rule on plain text or synced lrc
            text_to_check = plain_text or synced_lrc
            if not is_english_latin_lyrics(text_to_check):
                return {
                    "status": "none",
                    "synced_lines": [],
                    "plain_lines": [],
                    "is_instrumental": False,
                }

            # Parse synced lines if available
            synced_lines = parse_lrc_lines(synced_lrc) if synced_lrc else []
            plain_lines = [line.strip() for line in plain_text.splitlines() if line.strip()]

            if synced_lines:
                return {
                    "status": "synced",
                    "synced_lines": synced_lines,
                    "plain_lines": plain_lines,
                    "is_instrumental": False,
                }
            elif plain_lines:
                return {
                    "status": "plain",
                    "synced_lines": [],
                    "plain_lines": plain_lines,
                    "is_instrumental": False,
                }

            return {
                "status": "none",
                "synced_lines": [],
                "plain_lines": [],
                "is_instrumental": False,
            }

        except Exception as e:
            logger.error("Unexpected error in lyrics retrieval: %s", e)
            return {
                "status": "none",
                "synced_lines": [],
                "plain_lines": [],
                "is_instrumental": False,
            }
        finally:
            if should_close:
                await client.aclose()

    def _pick_best_candidate(
        self,
        candidates: Any,
        title: str,
        artist: str,
        target_duration: float,
    ) -> Optional[Dict[str, Any]]:
        if not isinstance(candidates, list) or not candidates:
            return None

        clean_t = title.lower()
        clean_a = artist.lower()

        best = None
        best_score = float("inf")

        for item in candidates:
            if not isinstance(item, dict):
                continue
            item_dur = float(item.get("duration") or 0)
            dur_diff = abs(item_dur - target_duration) if target_duration > 0 and item_dur > 0 else 10.0

            cand_t = (item.get("trackName") or item.get("name") or "").lower()
            cand_a = (item.get("artistName") or "").lower()

            # Match penalty
            name_penalty = 0.0
            if clean_t and clean_t not in cand_t and cand_t not in clean_t:
                name_penalty += 20.0
            if clean_a and clean_a not in cand_a and cand_a not in clean_a:
                name_penalty += 15.0

            # Prefer candidates with synced lyrics
            bonus = -10.0 if item.get("syncedLyrics") else 0.0

            total_penalty = dur_diff + name_penalty + bonus
            if total_penalty < best_score:
                best_score = total_penalty
                best = item

        return best
