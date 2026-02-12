import asyncio
import inspect
import os
import re
import shutil
import subprocess
import tempfile

import edge_tts
from dotenv import load_dotenv

load_dotenv()

TTS_VOICE = os.getenv("TTS_VOICE", "en-US-AriaNeural")
TTS_RATE = os.getenv("TTS_RATE", "-10%")
TTS_VOLUME = os.getenv("TTS_VOLUME", "+0%")
TTS_FALLBACK_RATE = int(os.getenv("TTS_FALLBACK_RATE", "-1"))


def _resolve_ffmpeg_binary():
    ffmpeg_bin = shutil.which("ffmpeg")
    if ffmpeg_bin:
        return ffmpeg_bin
    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        return get_ffmpeg_exe()
    except Exception:
        return None


def _clean_script_for_speech(script_text: str) -> str:
    lines = [line.strip() for line in script_text.splitlines() if line.strip()]
    narration = [line for line in lines if not line.startswith("[VISUAL]:")]
    narration = [
        re.sub(r"^(narration|scene|line)\s*(\d+)?\s*[:\-]\s*", "", line, flags=re.IGNORECASE)
        for line in narration
    ]
    narration = [re.sub(r"^(narration|scene|line)\s+(\d+)\.?\s*", "", line, flags=re.IGNORECASE) for line in narration]
    text = " ".join(narration) if narration else re.sub(r"\[VISUAL\]:", "", script_text)
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"([.!?])\s+", r"\1  ", text)
    return text


async def _generate_with_edge(text: str, output_file: str) -> str:
    supported = set(inspect.signature(edge_tts.Communicate.__init__).parameters)
    kwargs = {"rate": TTS_RATE, "volume": TTS_VOLUME}
    if "pitch" in supported:
        kwargs["pitch"] = os.getenv("TTS_PITCH", "+0Hz")

    communicate = edge_tts.Communicate(text, TTS_VOICE, **kwargs)
    await communicate.save(output_file)
    return output_file


def _generate_with_windows_tts(text: str, output_file: str) -> str:
    base, ext = os.path.splitext(output_file)
    wav_file = output_file if ext.lower() == ".wav" else f"{base}.wav"

    escaped_path = wav_file.replace("'", "''")
    rate = max(-10, min(10, TTS_FALLBACK_RATE))

    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w", encoding="utf-8") as tf:
        tf.write(text)
        text_file = tf.name
    escaped_text_file = text_file.replace("'", "''")

    ps_cmd = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Rate={rate}; "
        "$t = Get-Content -Raw -LiteralPath '" + escaped_text_file + "'; "
        "$s.SetOutputToWaveFile('" + escaped_path + "'); "
        "$s.Speak($t); "
        "$s.Dispose();"
    )

    r = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
    try:
        os.remove(text_file)
    except OSError:
        pass
    if r.returncode != 0 or not os.path.exists(wav_file):
        raise RuntimeError(f"Windows TTS fallback failed: {r.stderr}")

    if ext.lower() == ".mp3":
        ffmpeg_bin = _resolve_ffmpeg_binary()
        if ffmpeg_bin:
            c = subprocess.run([ffmpeg_bin, "-y", "-i", wav_file, output_file], capture_output=True, text=True)
            if c.returncode == 0 and os.path.exists(output_file):
                try:
                    os.remove(wav_file)
                except OSError:
                    pass
                return output_file

    return wav_file


async def generate_voiceover(script_text: str, output_file: str = "voiceover.mp3") -> str:
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)
    clean_text = _clean_script_for_speech(script_text)

    try:
        out = await _generate_with_edge(clean_text, output_file)
        print(f"Voiceover saved: {out}")
        return out
    except Exception as exc:
        print(f"[WARN] Edge TTS failed ({exc}). Falling back to Windows offline TTS.")
        out = _generate_with_windows_tts(clean_text, output_file)
        print(f"Voiceover saved (fallback): {out}")
        return out


def generate_voiceover_sync(script_text: str, output_file: str = "voiceover.mp3") -> str:
    try:
        return asyncio.run(generate_voiceover(script_text, output_file))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(generate_voiceover(script_text, output_file))
        finally:
            loop.close()
