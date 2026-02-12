import json
import os
import re
from typing import Dict, List


def _narration_lines(script_text: str) -> List[str]:
    lines = [line.strip() for line in script_text.splitlines() if line.strip()]
    return [line for line in lines if not line.startswith("[VISUAL]:")]


def _sanitize_topic(topic: str) -> str:
    return re.sub(r"\s+", " ", topic).strip()


def generate_seo_metadata(topic: str, script_text: str, output_path: str = "outputs/metadata.json") -> Dict:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    clean_topic = _sanitize_topic(topic)
    narration = _narration_lines(script_text)

    title = f"{clean_topic}: What You Need to Know in 60 Seconds"
    if len(title) > 100:
        title = title[:97] + "..."

    teaser = " ".join(narration[:3]).strip()
    description = (
        f"{teaser}\n\n"
        f"In this video, we break down {clean_topic} with practical examples and visuals.\n"
        "If you found this useful, like, comment, and subscribe for more AI explainers."
    )

    base_tags = [
        "artificial intelligence",
        "ai",
        "technology",
        "future tech",
        "automation",
        "machine learning",
        "explainer",
        "short video",
        clean_topic.lower(),
    ]
    tags = sorted({tag.strip() for tag in base_tags if tag.strip()})

    metadata = {
        "title": title,
        "description": description,
        "tags": tags,
        "categoryId": "28",
        "defaultLanguage": "en",
        "privacyStatus": os.getenv("YOUTUBE_PRIVACY_STATUS", "private"),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    txt_path = output_path.replace(".json", ".txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"TITLE\n{metadata['title']}\n\n")
        f.write(f"DESCRIPTION\n{metadata['description']}\n\n")
        f.write("TAGS\n" + ", ".join(metadata["tags"]) + "\n")

    return metadata
