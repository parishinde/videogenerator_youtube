import os
import sys
import time

from script_generator import extract_visuals_and_narration, generate_script
from video_creator import create_video
from visual_fetcher import fetch_visuals
from voice_generator import generate_voiceover_sync


def run_pipeline(topic):
    """Complete end-to-end 60-second video generation pipeline."""
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

    print("STEP 1/4: Generating script...")
    script = generate_script(topic)
    visuals, narration = extract_visuals_and_narration(script, topic)
    print(f"   Generated {len(visuals)} visuals and {len(narration)} narration lines")

    with open("outputs/script.txt", "w", encoding="utf-8") as f:
        f.write(script)
    print("   Script saved to outputs/script.txt")

    print("\nSTEP 2/4: Creating voiceover...")
    audio_file = generate_voiceover_sync(script, "outputs/voiceover.mp3")

    expected_visuals = int(os.getenv("MAX_VISUAL_DOWNLOADS", "4"))

    print("\nSTEP 3/4: Downloading visuals...")
    video_files = fetch_visuals(script, "visuals")
    print(f"   Downloaded {len(video_files)} videos")

    print("\nSTEP 4/4: Assembling video...")
    output_filename = f"outputs/{topic.replace(' ', '_')}_final.mp4"
    final_video = create_video(
        video_files,
        audio_file,
        output_filename,
        target_duration=target_duration,
        expected_clips=expected_visuals,
    )

    total_time = time.time() - start_time

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"Final video: {final_video}")
    print(f"Runtime: {total_time:.1f}s")
    print(f"Script: outputs/script.txt")
    print(f"Voiceover: {audio_file}")
    print(f"Video: {output_filename}")
    print("=" * 60 + "\n")

    return final_video


if __name__ == "__main__":
    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:])
    else:
        topic = input("Enter video topic: ")

    run_pipeline(topic)
