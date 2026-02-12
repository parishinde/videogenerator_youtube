# AI Video Pipeline

Generate short narrated videos from a topic using:

- Gemini (script generation)
- Edge TTS (with Windows offline fallback)
- Pexels API (stock visuals)
- FFmpeg (final assembly)

## Project Structure

- `pipeline.py`: Orchestrates the full flow.
- `script_generator.py`: Creates script with `[VISUAL]` scene lines + narration lines.
- `voice_generator.py`: Generates voiceover (`edge-tts` primary, Windows TTS fallback).
- `visual_fetcher.py`: Fetches scene videos from Pexels.
- `video_creator.py`: Assembles final video with FFmpeg.
- `outputs/`: Generated script, voiceover, final video.

## Requirements

- Python 3.12
- FFmpeg available (either on PATH or via `imageio-ffmpeg` package)
- Internet for Gemini + Pexels + Edge TTS

Install dependencies:

```powershell
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

## Environment Variables

Create/update `.env` in `ai-video-pipeline/`:

```env
GEMINI_API_KEY=your_gemini_api_key
PEXELS_API_KEY=your_pexels_api_key

# Optional model override
GEMINI_MODEL=gemini-1.5-flash

# TTS settings
TTS_VOICE=en-US-AriaNeural
TTS_RATE=+0%
TTS_PITCH=+0Hz
TTS_VOLUME=+2%
TTS_FALLBACK_RATE=-1

# Visual settings
MAX_VISUAL_DOWNLOADS=8

# Duration settings
# 0 = auto-match voiceover duration
TARGET_VIDEO_DURATION_SECONDS=0
TARGET_AUDIO_DURATION_SECONDS=30
```

## Run

```powershell
python pipeline.py "How Artificial Intelligence Is Changing Everyday Life"
```

## Output

After a run:

- `outputs/script.txt`
- `outputs/voiceover.mp3`
- `outputs/<topic>_final.mp4`

## How It Works

1. Generate script from topic (`script_generator.py`).
2. Generate voiceover (`voice_generator.py`).
3. Download scene clips from Pexels (`visual_fetcher.py`).
4. Assemble final video and mux narration audio (`video_creator.py`).

## Troubleshooting

### 1) `404 model ... not found`

- Model availability changes by account/API version.
- Keep `GEMINI_MODEL` set to a supported model or remove it to let fallback logic choose.

### 2) `edge-tts` 403 websocket error

- This is common on some networks.
- Pipeline automatically falls back to Windows offline TTS.

### 3) Audio/video mismatch (audio faster/slower)

- Set `TARGET_VIDEO_DURATION_SECONDS=0` to auto-match voiceover duration.

### 4) Wrong/mismatched visuals

- Increase relevance by improving `[VISUAL]` lines in script.
- `MAX_VISUAL_DOWNLOADS=8` gives one clip per scene.

## Notes

- If Pexels download fails for some scenes, fallback clips are created so assembly can still complete.
- Final assembly currently uses FFmpeg backend for stability.
