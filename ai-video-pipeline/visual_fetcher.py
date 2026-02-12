import os
import re
import time
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
PEXELS_VIDEO_SEARCH_URL = "https://api.pexels.com/videos/search"
MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
MAX_DOWNLOAD_SECONDS = 20
MAX_VISUAL_DOWNLOADS = int(os.getenv("MAX_VISUAL_DOWNLOADS", "4"))

DOMAIN_HINTS = {
    "healthcare": ["hospital", "doctor", "patient", "medical", "clinic", "surgery"],
    "medical": ["hospital", "doctor", "patient", "medical", "clinic", "surgery"],
    "robot": ["robot", "technology"],
    "ai": ["technology", "digital"],
}


def extract_keywords(script_text: str) -> list[str]:
    keywords: list[str] = []
    stopwords = {
        "a", "an", "the", "and", "with", "in", "on", "of", "to", "for", "through",
        "allows", "allow", "enhance", "enhancing", "improve", "improving", "small", "worldwide",
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
    response = requests.get(PEXELS_VIDEO_SEARCH_URL, headers=headers, params=params, timeout=20)
    response.raise_for_status()
    return response.json().get("videos", [])


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _score_video(video: dict, query: str) -> int:
    q = _tokenize(query)
    slug = _tokenize(video.get("url", ""))
    overlap = len(q & slug)
    title_overlap = len(q & _tokenize(video.get("user", {}).get("name", "")))
    duration = int(video.get("duration", 0) or 0)
    duration_bonus = 1 if 4 <= duration <= 15 else 0
    return overlap * 10 + title_overlap * 2 + duration_bonus


def _pick_video_url(video: dict) -> Optional[str]:
    files = video.get("video_files", [])
    mp4_files = [f for f in files if f.get("file_type") == "video/mp4" and f.get("link")]
    if not mp4_files:
        return None
    preferred = sorted(mp4_files, key=lambda f: (f.get("width") or 1280) * (f.get("height") or 720))
    return preferred[0].get("link")


def _select_best_video(search_query: str, used_ids: set[int]) -> Optional[dict]:
    videos = _search_video(search_query)
    if not videos:
        return None
    candidates = [v for v in videos if v.get("id") not in used_ids] or videos
    ranked = sorted(candidates, key=lambda v: _score_video(v, search_query), reverse=True)
    return ranked[0] if ranked else None


def download_video(search_query: str, output_path: str, used_ids: set[int]) -> bool:
    try:
        video = _select_best_video(search_query, used_ids)
        if not video:
            print(f"No video found for: {search_query}")
            return False

        video_id = video.get("id")
        if video_id is not None:
            used_ids.add(video_id)

        video_url = _pick_video_url(video)
        if not video_url:
            print(f"No usable video file for: {search_query}")
            return False

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

        print(f"Downloaded: {output_path}")
        return True
    except Exception as exc:
        if os.path.exists(output_path):
            try:
                os.remove(output_path)
            except OSError:
                pass
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

    for i, keyword in enumerate(keywords):
        output_path = os.path.join(output_folder, f"video_{i + 1}.mp4")
        try:
            ok = download_video(keyword, output_path, used_ids)
        except KeyboardInterrupt:
            print("Visual download interrupted. Continuing with downloaded clips.")
            break
        if ok:
            downloaded.append(output_path)

    return downloaded


if __name__ == "__main__":
    sample = """[VISUAL]: A robotic arm in surgery\n[VISUAL]: Robot in hospital hallway\n"""
    print(fetch_visuals(sample))
