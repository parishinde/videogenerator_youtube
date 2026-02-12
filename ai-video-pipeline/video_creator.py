import os
import shutil
import subprocess
from typing import Optional

from PIL import Image

if not hasattr(Image, "ANTIALIAS") and hasattr(Image, "Resampling"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS


def _resolve_ffmpeg_bin() -> Optional[str]:
    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        return get_ffmpeg_exe()
    except Exception:
        return None


def _resolve_ffprobe_bin(ffmpeg_bin: Optional[str]) -> Optional[str]:
    probe = shutil.which("ffprobe")
    if probe:
        return probe
    if ffmpeg_bin:
        candidate = ffmpeg_bin.replace("ffmpeg", "ffprobe")
        if os.path.exists(candidate):
            return candidate
    return None


def get_video_duration(video_path: str) -> float:
    ffmpeg_bin = _resolve_ffmpeg_bin()
    ffprobe_bin = _resolve_ffprobe_bin(ffmpeg_bin)
    if not ffprobe_bin:
        return 0.0

    result = subprocess.run(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            video_path,
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def get_media_duration(path: str) -> float:
    ffmpeg_bin = _resolve_ffmpeg_bin()
    ffprobe_bin = _resolve_ffprobe_bin(ffmpeg_bin)
    if not ffprobe_bin or not os.path.exists(path):
        return 0.0
    result = subprocess.run(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            path,
        ],
        capture_output=True,
        text=True,
    )
    try:
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def ensure_exact_duration(video_path: str, target_duration: float, ffmpeg_bin: str) -> str:
    duration = get_video_duration(video_path)
    if duration > 0 and abs(duration - target_duration) < 0.1:
        return video_path

    output_path = video_path.replace(".mp4", f"_{target_duration:.2f}s.mp4")
    # Re-encode every prepared clip to avoid pause/freeze artifacts at boundaries.
    # Copy-trimming often cuts on non-keyframes and causes visible hiccups.
    input_args = ["-i", video_path] if duration > target_duration else ["-stream_loop", "-1", "-i", video_path]
    cmd = [
        ffmpeg_bin,
        *input_args,
        "-t",
        str(target_duration),
        "-vf",
        "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=24,format=yuv420p",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-movflags",
        "+faststart",
        "-y",
        output_path,
    ]
    _run(cmd)
    return output_path if os.path.exists(output_path) else video_path


def create_fallback_clip(index: int, duration: float, ffmpeg_bin: str) -> str:
    output_path = f"temp_fallback_{index}.mp4"
    colors = ["blue", "green", "red", "purple", "orange", "cyan", "magenta", "yellow"]
    color = colors[index % len(colors)]
    cmd = [
        ffmpeg_bin,
        "-f",
        "lavfi",
        "-i",
        f"color=c={color}:s=1280x720:d={duration}",
        "-vf",
        f"drawtext=text='Scene {index+1}':fontcolor=white:fontsize=56:x=(w-text_w)/2:y=(h-text_h)/2",
        "-c:v",
        "libx264",
        "-t",
        str(duration),
        "-y",
        output_path,
    ]
    _run(cmd)
    return output_path


def _prepare_final_audio(ffmpeg_bin: str, input_audio: str, output_audio: str, target_duration: float) -> bool:
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i",
        input_audio,
        "-af",
        f"loudnorm=I=-16:TP=-1.5:LRA=11,volume=4dB,apad,atrim=0:{target_duration}",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        output_audio,
    ]
    r = _run(cmd)
    return r.returncode == 0 and os.path.exists(output_audio)


def _ensure_clip_count(video_files: list[str], expected_clips: int, per_clip: float, ffmpeg_bin: str) -> list[str]:
    existing = [v for v in video_files if v and os.path.exists(v)]
    clips = existing[:expected_clips]
    while len(clips) < expected_clips:
        clips.append(create_fallback_clip(len(clips), per_clip, ffmpeg_bin))
    return clips


def create_video_with_moviepy(
    video_files,
    audio_file,
    output_file="final_video.mp4",
    target_duration=60,
    expected_clips=4,
):
    from moviepy.editor import AudioFileClip, VideoFileClip, concatenate_videoclips

    ffmpeg_bin = _resolve_ffmpeg_bin()
    if not ffmpeg_bin:
        raise RuntimeError("FFmpeg binary not found. Install ffmpeg or imageio-ffmpeg.")

    final_duration = float(target_duration)
    clip_count = max(1, int(expected_clips))
    target_per_clip = final_duration / clip_count

    source_files = _ensure_clip_count(video_files or [], clip_count, target_per_clip, ffmpeg_bin)

    audio_clip = AudioFileClip(audio_file)
    video_clips = []
    for i, video_file in enumerate(source_files):
        clip = VideoFileClip(video_file)
        clip = clip.resize(height=720)
        clip = clip.crop(x_center=clip.w / 2, y_center=clip.h / 2, width=1280, height=720)
        clip = clip.subclip(0, min(clip.duration, target_per_clip))
        if clip.duration < target_per_clip:
            clip = clip.loop(duration=target_per_clip)
        video_clips.append(clip)

    final_video = concatenate_videoclips(video_clips, method="compose")
    final_video = final_video.subclip(0, min(final_video.duration, final_duration))
    if final_video.duration < final_duration:
        final_video = final_video.loop(duration=final_duration)

    audio_for_video = audio_clip.subclip(0, min(audio_clip.duration, final_duration))
    if audio_for_video.duration < final_duration:
        audio_for_video = audio_for_video.audio_loop(duration=final_duration)

    final_video = final_video.set_audio(audio_for_video)

    temp_video = output_file.replace(".mp4", "_moviepy_temp.mp4")
    final_video.write_videofile(
        temp_video,
        codec="libx264",
        audio=True,
        audio_codec="aac",
        audio_fps=44100,
        fps=24,
        preset="medium",
        bitrate="2000k",
        verbose=False,
        logger=None,
    )

    audio_for_video.close()
    audio_clip.close()
    final_video.close()
    for clip in video_clips:
        clip.close()

    temp_audio = output_file.replace(".mp4", "_audio_temp.m4a")
    mux_audio = audio_file
    if _prepare_final_audio(ffmpeg_bin, audio_file, temp_audio, final_duration):
        mux_audio = temp_audio

    mux = _run(
        [
            ffmpeg_bin,
            "-y",
            "-i",
            temp_video,
            "-i",
            mux_audio,
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-b:a",
            "192k",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-t",
            str(final_duration),
            output_file,
        ]
    )

    if mux.returncode != 0 or not os.path.exists(output_file):
        # Keep at least moviepy output if remux fails.
        os.replace(temp_video, output_file)
    elif os.path.exists(temp_video):
        os.remove(temp_video)

    if os.path.exists(temp_audio):
        os.remove(temp_audio)

    return output_file


def create_video_ffmpeg(
    video_files,
    audio_file,
    output_file="final_video.mp4",
    target_duration=60,
    expected_clips=4,
):
    ffmpeg_bin = _resolve_ffmpeg_bin()
    if not ffmpeg_bin:
        raise RuntimeError("FFmpeg binary not found. Install ffmpeg or imageio-ffmpeg.")

    final_duration = float(target_duration) if target_duration and float(target_duration) > 0 else 0.0
    if final_duration <= 0:
        final_duration = get_media_duration(audio_file)
    if final_duration <= 0:
        final_duration = 30.0
    clip_count = max(1, int(expected_clips))
    per_clip = final_duration / clip_count

    source_files = _ensure_clip_count(video_files or [], clip_count, per_clip, ffmpeg_bin)
    processed = [ensure_exact_duration(v, per_clip, ffmpeg_bin) for v in source_files]

    with open("concat_list.txt", "w", encoding="utf-8") as f:
        for video in processed:
            f.write(f"file '{os.path.abspath(video)}'\n")

    temp_concat = "temp_concat.mp4"
    r1 = _run([ffmpeg_bin, "-f", "concat", "-safe", "0", "-i", "concat_list.txt", "-c", "copy", temp_concat, "-y"])
    if r1.returncode != 0:
        raise RuntimeError(f"Video concat failed: {r1.stderr}")

    temp_audio = output_file.replace(".mp4", "_audio_temp.m4a")
    mux_audio = audio_file
    if _prepare_final_audio(ffmpeg_bin, audio_file, temp_audio, final_duration):
        mux_audio = temp_audio

    r2 = _run(
        [
            ffmpeg_bin,
            "-i",
            temp_concat,
            "-i",
            mux_audio,
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-b:a",
            "192k",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-t",
            str(final_duration),
            output_file,
            "-y",
        ]
    )
    if r2.returncode != 0:
        raise RuntimeError(f"Final mux failed: {r2.stderr}")

    for path in ["concat_list.txt", temp_concat, temp_audio]:
        if os.path.exists(path):
            os.remove(path)

    return output_file


create_video = create_video_ffmpeg
print("Using FFmpeg for video creation")
