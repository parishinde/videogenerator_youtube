import os
import re
import shutil
import subprocess
from typing import List, Tuple


def _resolve_ffprobe_bin() -> str | None:
    probe = shutil.which("ffprobe")
    if probe:
        return probe
    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        ffmpeg_bin = get_ffmpeg_exe()
        candidate = ffmpeg_bin.replace("ffmpeg", "ffprobe")
        if os.path.exists(candidate):
            return candidate
    except Exception:
        pass
    return None


def _audio_duration(audio_file: str) -> float:
    probe = _resolve_ffprobe_bin()
    if not probe:
        return 60.0

    r = subprocess.run(
        [
            probe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            audio_file,
        ],
        capture_output=True,
        text=True,
    )
    try:
        return max(1.0, float(r.stdout.strip()))
    except Exception:
        return 60.0


def _lines(script_text: str) -> List[str]:
    lines = [line.strip() for line in script_text.splitlines() if line.strip()]
    return [line for line in lines if not line.startswith("[VISUAL]:")]


def _clean(line: str) -> str:
    line = re.sub(r"^(narration|scene|line)\s*(\d+)?\s*[:\-]\s*", "", line, flags=re.IGNORECASE)
    return line.strip()


def _ts(seconds: float, srt: bool = True) -> str:
    ms = int(round((seconds - int(seconds)) * 1000))
    total = int(seconds)
    hh = total // 3600
    mm = (total % 3600) // 60
    ss = total % 60
    if srt:
        return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"
    return f"{hh:02d}:{mm:02d}:{ss:02d}.{ms:03d}"


def generate_subtitles(
    script_text: str,
    audio_file: str,
    srt_path: str = "outputs/subtitles.srt",
    vtt_path: str = "outputs/subtitles.vtt",
) -> Tuple[str, str]:
    os.makedirs(os.path.dirname(srt_path) or ".", exist_ok=True)

    narration = [_clean(x) for x in _lines(script_text)]
    if not narration:
        narration = ["No narration text available."]

    duration = _audio_duration(audio_file)
    weights = [max(1, len(line)) for line in narration]
    total_weight = sum(weights)

    segments = []
    t = 0.0
    for line, w in zip(narration, weights):
        seg = duration * (w / total_weight)
        start = t
        end = min(duration, t + seg)
        segments.append((start, end, line))
        t = end

    if segments:
        start, _, text = segments[-1]
        segments[-1] = (start, duration, text)

    with open(srt_path, "w", encoding="utf-8") as srt:
        for i, (start, end, text) in enumerate(segments, start=1):
            srt.write(f"{i}\n{_ts(start, True)} --> {_ts(end, True)}\n{text}\n\n")

    with open(vtt_path, "w", encoding="utf-8") as vtt:
        vtt.write("WEBVTT\n\n")
        for start, end, text in segments:
            vtt.write(f"{_ts(start, False)} --> {_ts(end, False)}\n{text}\n\n")

    return srt_path, vtt_path
