import os
import re
from typing import List, Tuple

import google.generativeai as genai
from dotenv import load_dotenv
from google.api_core import exceptions as google_exceptions

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env file")

genai.configure(api_key=GEMINI_API_KEY)


def _is_allowed_model(name: str) -> bool:
    n = name.lower()
    blocked = ("preview", "research", "experimental", "thinking")
    return not any(x in n for x in blocked)


def _get_model_order() -> List[str]:
    preferred = os.getenv("GEMINI_MODEL", "").strip()
    available: List[str] = []

    try:
        available = sorted(
            {
                m.name.split("/")[-1]
                for m in genai.list_models()
                if "generateContent" in getattr(m, "supported_generation_methods", [])
            }
        )
    except Exception:
        available = []

    order: List[str] = []
    if preferred:
        order.append(preferred)

    defaults = ["gemini-1.5-flash", "gemini-1.5-flash-8b", "gemini-1.5-pro", "gemini-2.0-flash"]
    for m in defaults:
        if m not in order:
            order.append(m)

    for m in available:
        if m not in order and _is_allowed_model(m):
            order.append(m)

    return order


def _fallback_script(topic: str) -> str:
    return f"""[VISUAL]: Wide establishing shot of {topic} in action
{topic} is revolutionizing how we live and work.
[VISUAL]: Close-up details showing the intricate components of {topic}
Every day, new breakthroughs are being made in this field.
[VISUAL]: People interacting with {topic} technology in daily life
The applications span healthcare, education, and entertainment.
[VISUAL]: Scientists and engineers developing next-generation {topic}
Research teams worldwide are pushing the boundaries.
[VISUAL]: Abstract visualization of {topic} concepts and data flow
The underlying technology becomes more sophisticated each year.
[VISUAL]: Comparison of old methods versus modern {topic} solutions
What once took days now happens in seconds.
[VISUAL]: Future vision of how {topic} will evolve
Experts predict exponential growth in capabilities.
[VISUAL]: Inspiring shot of {topic} improving quality of life
Join us as we explore this transformative technology.
"""


def generate_script(topic: str) -> str:
    """Generate a 60-second script with 8 visual cues and 8 narration lines."""
    prompt = f"""Write a 60-second video script about {topic}.

REQUIREMENTS:
- EXACTLY 8 visuals and 8 narration lines
- Each visual line must start with [VISUAL]:
- Every [VISUAL] line must be followed by one narration line
- Visuals should be specific and different
- Narration should be conversational and concise
- Do NOT include labels like 'Narration 1', 'Scene 1', numbering, or bullet points

Output format (strict):
[VISUAL]: Scene 1 description
A natural spoken sentence for scene 1.
...
[VISUAL]: Scene 8 description
A natural spoken sentence for scene 8.
"""

    saw_quota = False
    for model_name in _get_model_order():
        if not _is_allowed_model(model_name):
            continue
        try:
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            text = (response.text or "").strip()
            if text:
                return _sanitize_script_text(text)
        except google_exceptions.NotFound:
            continue
        except google_exceptions.ResourceExhausted:
            saw_quota = True
            continue
        except Exception:
            continue

    if saw_quota:
        print("[WARN] Gemini quota exceeded. Using local fallback script.")
    else:
        print("[WARN] No compatible Gemini model available. Using local fallback script.")
    return _sanitize_script_text(_fallback_script(topic))


def _sanitize_script_text(script_text: str) -> str:
    """Remove generic narration/scene labels so TTS reads natural sentences."""
    cleaned_lines = []
    for raw in script_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        # Strip labels like "Narration:", "Narration 1:", "Scene 2 -", "Line 3:"
        line = re.sub(r"^(narration|scene|line)\s*(\d+)?\s*[:\-]\s*", "", line, flags=re.IGNORECASE)
        line = re.sub(r"^(narration|scene|line)\s+(\d+)\.?\s*", "", line, flags=re.IGNORECASE)
        line = re.sub(r"^\d+\s*[:\-]\s*", "", line)
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


def extract_visuals_and_narration(script_text: str, topic: str = "technology") -> Tuple[List[str], List[str]]:
    visuals: List[str] = []
    narration: List[str] = []
    lines = [line.strip() for line in script_text.splitlines() if line.strip()]

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("[VISUAL]:"):
            visuals.append(line.replace("[VISUAL]:", "", 1).strip())
            if i + 1 < len(lines) and not lines[i + 1].startswith("[VISUAL]:"):
                narration.append(lines[i + 1])
                i += 1
        i += 1

    while len(visuals) < 8:
        visuals.append(f"{topic} technology showcase")
    while len(narration) < 8:
        narration.append(f"{topic} continues to advance rapidly.")

    return visuals[:8], narration[:8]


if __name__ == "__main__":
    import sys

    topic = sys.argv[1] if len(sys.argv) > 1 else "artificial intelligence"
    script = generate_script(topic)
    print(script)
    v, n = extract_visuals_and_narration(script, topic)
    print(f"Visuals: {len(v)} | Narration: {len(n)}")
