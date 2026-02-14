import json
import os
import re
import shutil
import time
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
PEXELS_VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"

MAX_DOWNLOAD_BYTES = int(os.getenv("MAX_DOWNLOAD_BYTES", str(8 * 1024 * 1024)))
MAX_DOWNLOAD_SECONDS = int(os.getenv("MAX_DOWNLOAD_SECONDS", "20"))
MAX_VISUAL_DOWNLOADS = int(os.getenv("MAX_VISUAL_DOWNLOADS", "8"))

PEXELS_MAX_RETRIES = int(os.getenv("PEXELS_MAX_RETRIES", "3"))
PEXELS_RETRY_BACKOFF_SECONDS = float(os.getenv("PEXELS_RETRY_BACKOFF_SECONDS", "1.5"))

ENABLE_VISUAL_CACHE = os.getenv("ENABLE_VISUAL_CACHE", "1") == "1"
VISUAL_CACHE_DIR = os.getenv("VISUAL_CACHE_DIR", "visuals/cache")
VISUAL_QUALITY_LOG_PATH = os.getenv("VISUAL_QUALITY_LOG_PATH", "outputs/visual_quality_log.jsonl")

DOMAIN_HINTS = {
    "healthcare": ["hospital", "doctor", "patient", "medical", "clinic", "surgery"],
    "medical": ["hospital", "doctor", "patient", "medical", "clinic", "surgery"],
    "robot": ["robot", "technology"],
    "ai": ["technology", "digital"],
}


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _safe_filename(text: str, max_len: int = 80) -> str:
    text = re.sub(r"[^a-zA-Z0-9_-]+", "_", text.strip().lower())
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:max_len] or "query"


def _append_quality_log(record: dict) -> None:
    try:
        os.makedirs(os.path.dirname(VISUAL_QUALITY_LOG_PATH) or ".", exist_ok=True)
        with open(VISUAL_QUALITY_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def extract_keywords(script_text: str) -> list[str]:
    keywords: list[str] = []
    stopwords = {
        "a",
        "an",
        "the",
        "and",
        "with",
        "in",
        "on",
        "of",
        "to",
        "for",
        "through",
        "allows",
        "allow",
        "enhance",
        "enhancing",
        "improve",
        "improving",
        "small",
        "worldwide",
    }

    lines = [line.strip() for line in script_text.splitlines() if line.strip()]
    for i, line in enumerate(lines):
        if not line.startswith("[VISUAL]:"):
            continue

        visual_desc = line.replace("[VISUAL]:", "", 1).strip()
        narration = ""
        if i + 1 < len(lines) and not lines[i + 1].startswith("[VISUAL]:"):
            narration = lines[i + 1].strip()

        combined = f"{visual_desc} {narration}".lower()
        words = [w.strip(".,") for w in combined.split()]
        filtered = [w for w in words if w and w not in stopwords]
        query_terms = filtered[:7]

        for trigger, hints in DOMAIN_HINTS.items():
            if trigger in combined:
                for hint in hints:
                    if hint not in query_terms:
                        query_terms.append(hint)

        search_term = " ".join(query_terms[:10]).strip()
        if search_term:
            keywords.append(search_term)

    return keywords[:MAX_VISUAL_DOWNLOADS]


def _search_video(search_query: str) -> list[dict]:
    headers = {"Authorization": PEXELS_API_KEY}
    params = {"query": search_query, "per_page": 10, "page": 1}

    last_exc: Optional[Exception] = None
    for attempt in range(1, PEXELS_MAX_RETRIES + 1):
        try:
            response = requests.get(PEXELS_VIDEO_SEARCH_URL, headers=headers, params=params, timeout=20)
            response.raise_for_status()
            return response.json().get("videos", [])
        except Exception as exc:
            last_exc = exc
            if attempt < PEXELS_MAX_RETRIES:
                time.sleep(PEXELS_RETRY_BACKOFF_SECONDS * attempt)

    raise RuntimeError(f"Pexels search failed after {PEXELS_MAX_RETRIES} attempts: {last_exc}")


def _score_video(video: dict, query: str) -> dict:
    q = _tokenize(query)
    slug = _tokenize(video.get("url", ""))
    overlap = len(q & slug)
    title_overlap = len(q & _tokenize(video.get("user", {}).get("name", "")))
    duration = int(video.get("duration", 0) or 0)
    duration_bonus = 1 if 4 <= duration <= 15 else 0
    score = overlap * 10 + title_overlap * 2 + duration_bonus
    return {
        "score": score,
        "overlap": overlap,
        "title_overlap": title_overlap,
        "duration": duration,
        "duration_bonus": duration_bonus,
    }


def _pick_video_url(video: dict) -> Optional[str]:
    files = video.get("video_files", [])
    mp4_files = [f for f in files if f.get("file_type") == "video/mp4" and f.get("link")]
    if not mp4_files:
        return None

    preferred = sorted(
        mp4_files,
        key=lambda f: ((f.get("width") or 1280) * (f.get("height") or 720), abs((f.get("height") or 720) - 720)),
    )
    return preferred[0].get("link")


def _select_best_video(search_query: str, used_ids: set[int]) -> tuple[Optional[dict], Optional[dict]]:
    videos = _search_video(search_query)
    if not videos:
        return None, None

    candidates = [v for v in videos if v.get("id") not in used_ids] or videos
    scored = [(v, _score_video(v, search_query)) for v in candidates]
    scored.sort(key=lambda x: x[1]["score"], reverse=True)

    best_video, best_score = scored[0]
    return best_video, best_score


def _store_in_cache(local_file: str, search_query: str, video_id: Optional[int]) -> Optional[str]:
    if not ENABLE_VISUAL_CACHE:
        return None
    try:
        os.makedirs(VISUAL_CACHE_DIR, exist_ok=True)
        stamp = int(time.time())
        cache_name = f"{video_id or 'local'}_{_safe_filename(search_query)}_{stamp}.mp4"
        cache_path = os.path.join(VISUAL_CACHE_DIR, cache_name)
        shutil.copy2(local_file, cache_path)
        return cache_path
    except Exception:
        return None


def _find_cached_clip(search_query: str) -> Optional[str]:
    if not ENABLE_VISUAL_CACHE or not os.path.isdir(VISUAL_CACHE_DIR):
        return None

    query_tokens = _tokenize(search_query)
    best_path = None
    best_score = -1

    for name in os.listdir(VISUAL_CACHE_DIR):
        if not name.lower().endswith(".mp4"):
            continue
        path = os.path.join(VISUAL_CACHE_DIR, name)
        score = len(query_tokens & _tokenize(name))
        if score > best_score:
            best_score = score
            best_path = path

    if best_score <= 0:
        return None
    return best_path


def _download_with_retry(video_url: str, output_path: str) -> None:
    last_exc: Optional[Exception] = None

    for attempt in range(1, PEXELS_MAX_RETRIES + 1):
        try:
            start = time.monotonic()
            with requests.get(video_url, timeout=(8, 8), stream=True) as response:
                response.raise_for_status()
                total = 0
                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        if time.monotonic() - start > MAX_DOWNLOAD_SECONDS:
                            raise TimeoutError("Video download exceeded time limit.")
                        total += len(chunk)
                        if total > MAX_DOWNLOAD_BYTES:
                            raise TimeoutError("Video too large for quick pipeline run.")
                        f.write(chunk)
            return
        except Exception as exc:
            last_exc = exc
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
            if attempt < PEXELS_MAX_RETRIES:
                time.sleep(PEXELS_RETRY_BACKOFF_SECONDS * attempt)

    raise RuntimeError(f"Video download failed after {PEXELS_MAX_RETRIES} attempts: {last_exc}")


def download_video(search_query: str, output_path: str, used_ids: set[int], scene_index: int) -> bool:
    log_record = {
        "scene": scene_index,
        "query": search_query,
        "source": None,
        "video_id": None,
        "score": None,
        "status": "failed",
        "output": output_path,
        "timestamp": int(time.time()),
    }

    try:
        video, score_data = _select_best_video(search_query, used_ids)
        if not video:
            raise RuntimeError("No video candidates returned")

        video_id = video.get("id")
        video_url = _pick_video_url(video)
        if not video_url:
            raise RuntimeError("No usable MP4 URL")

        _download_with_retry(video_url, output_path)

        if video_id is not None:
            used_ids.add(video_id)

        _store_in_cache(output_path, search_query, video_id)

        log_record.update(
            {
                "source": "pexels",
                "video_id": video_id,
                "score": score_data,
                "status": "ok",
            }
        )
        _append_quality_log(log_record)
        print(f"Downloaded: {output_path}")
        return True

    except Exception as exc:
        cached = _find_cached_clip(search_query)
        if cached:
            try:
                shutil.copy2(cached, output_path)
                log_record.update(
                    {
                        "source": "cache_fallback",
                        "status": "ok",
                        "cache_path": cached,
                        "error": str(exc),
                    }
                )
                _append_quality_log(log_record)
                print(f"Used cached clip for '{search_query}': {output_path}")
                return True
            except Exception as cache_exc:
                log_record["cache_error"] = str(cache_exc)

        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                pass

        log_record.update({"status": "failed", "error": str(exc), "source": "none"})
        _append_quality_log(log_record)
        print(f"Failed to download '{search_query}': {exc}")
        return False


def fetch_visuals(script_text: str, output_folder: str = "visuals") -> list[str]:
    if not PEXELS_API_KEY:
        print("PEXELS_API_KEY is missing in .env. Skipping visual download.")
        return []

    os.makedirs(output_folder, exist_ok=True)
    keywords = extract_keywords(script_text)
    downloaded: list[str] = []
    used_ids: set[int] = set()

    for i, keyword in enumerate(keywords, start=1):
        output_path = os.path.join(output_folder, f"video_{i}.mp4")
        try:
            ok = download_video(keyword, output_path, used_ids, scene_index=i)
        except KeyboardInterrupt:
            print("Visual download interrupted. Continuing with downloaded clips.")
            break
        if ok:
            downloaded.append(output_path)

    return downloaded


if __name__ == "__main__":
    sample = """[VISUAL]: A robotic arm in surgery\n[VISUAL]: Robot in hospital hallway\n"""
    print(fetch_visuals(sample))
