import json
import os
import sys
import time

from metadata_generator import generate_seo_metadata
from script_generator import extract_visuals_and_narration, generate_script
from subtitle_generator import generate_subtitles
from thumbnail_generator import create_thumbnail
from video_creator import create_video
from visual_fetcher import fetch_visuals
from voice_generator import generate_voiceover_sync
from youtube_uploader import upload_video_to_youtube


def run_pipeline(topic):
    """Complete end-to-end AI video generation pipeline."""
    start_time = time.time()
    target_duration = float(os.getenv("TARGET_VIDEO_DURATION_SECONDS", "0"))

    os.makedirs("outputs", exist_ok=True)
    os.makedirs("visuals", exist_ok=True)

    print("\n" + "=" * 60)
    print("AI VIDEO GENERATION PIPELINE")
    print(f"Topic: {topic}")
    if target_duration > 0:
        print(f"Target: {target_duration:.0f} seconds with up to 8 visuals")
    else:
        print("Target: match visual timeline to voiceover duration")
    print("=" * 60 + "\n")

    print("STEP 1/8: Generating script...")
    script = generate_script(topic)
    visuals, narration = extract_visuals_and_narration(script, topic)
    print(f"   Generated {len(visuals)} visuals and {len(narration)} narration lines")

    with open("outputs/script.txt", "w", encoding="utf-8") as f:
        f.write(script)
    print("   Script saved to outputs/script.txt")

    print("\nSTEP 2/8: Creating voiceover...")
    audio_file = generate_voiceover_sync(script, "outputs/voiceover.mp3")

    expected_visuals = int(os.getenv("MAX_VISUAL_DOWNLOADS", "8"))

    print("\nSTEP 3/8: Downloading visuals...")
    video_files = fetch_visuals(script, "visuals")
    print(f"   Downloaded {len(video_files)} videos")

    print("\nSTEP 4/8: Assembling video...")
    output_filename = f"outputs/{topic.replace(' ', '_')}_final.mp4"
    final_video = create_video(
        video_files,
        audio_file,
        output_filename,
        target_duration=target_duration,
        expected_clips=expected_visuals,
    )

    print("\nSTEP 5/8: Generating thumbnail...")
    thumbnail_file = create_thumbnail(topic, "outputs/thumbnail.jpg")
    print(f"   Thumbnail: {thumbnail_file}")

    print("\nSTEP 6/8: Generating SEO metadata...")
    metadata = generate_seo_metadata(topic, script, "outputs/metadata.json")
    print("   Metadata: outputs/metadata.json")

    print("\nSTEP 7/8: Generating subtitles...")
    srt_file, vtt_file = generate_subtitles(script, audio_file, "outputs/subtitles.srt", "outputs/subtitles.vtt")
    print(f"   Subtitles: {srt_file}, {vtt_file}")

    youtube_url = None
    if os.getenv("ENABLE_YOUTUBE_UPLOAD", "0") == "1":
        print("\nSTEP 8/8: Uploading to YouTube...")
        youtube_url = upload_video_to_youtube(
            final_video,
            metadata,
            thumbnail_file=thumbnail_file,
            subtitles_file=srt_file,
        )
        print(f"   YouTube URL: {youtube_url or 'Upload failed'}")
    else:
        print("\nSTEP 8/8: YouTube upload skipped (ENABLE_YOUTUBE_UPLOAD=0)")

    total_time = time.time() - start_time

    with open("outputs/pipeline_summary.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "topic": topic,
                "video": final_video,
                "script": "outputs/script.txt",
                "voiceover": audio_file,
                "thumbnail": thumbnail_file,
                "metadata": "outputs/metadata.json",
                "subtitles": {"srt": srt_file, "vtt": vtt_file},
                "youtube_url": youtube_url,
                "runtime_seconds": round(total_time, 2),
            },
            f,
            indent=2,
        )

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"Final video: {final_video}")
    print(f"Runtime: {total_time:.1f}s")
    print("Outputs:")
    print("  - outputs/script.txt")
    print(f"  - {audio_file}")
    print(f"  - {final_video}")
    print("  - outputs/thumbnail.jpg")
    print("  - outputs/metadata.json")
    print("  - outputs/subtitles.srt")
    print("  - outputs/subtitles.vtt")
    print("  - outputs/pipeline_summary.json")
    print("=" * 60 + "\n")

    return final_video


if __name__ == "__main__":
    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
    else:
        topic = input("Enter video topic: ")

    run_pipeline(topic)
