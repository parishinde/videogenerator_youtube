import os
from textwrap import wrap

from PIL import Image, ImageDraw, ImageFont


def _load_font(size: int):
    candidates = [
        "arialbd.ttf",
        "arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except Exception:
            continue
    return ImageFont.load_default()


def create_thumbnail(topic: str, output_path: str = "outputs/thumbnail.jpg") -> str:
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    width, height = 1280, 720
    img = Image.new("RGB", (width, height), "#0a1f44")
    draw = ImageDraw.Draw(img)

    # Simple layered background accents
    draw.rectangle([0, 0, width, int(height * 0.5)], fill="#102d66")
    draw.rectangle([0, int(height * 0.5), width, height], fill="#061633")
    draw.ellipse([900, -120, 1400, 380], fill="#1f4ea3")

    title = topic.strip().title()
    heading = "AI EXPLAINED"

    heading_font = _load_font(56)
    title_font = _load_font(72)

    draw.text((70, 70), heading, font=heading_font, fill="white")

    wrapped = wrap(title, width=24)
    y = 180
    for line in wrapped[:4]:
        draw.text((70, y), line, font=title_font, fill="#ffda57")
        y += 86

    draw.rectangle([70, height - 120, 520, height - 60], fill="#f04f4f")
    cta_font = _load_font(42)
    draw.text((92, height - 113), "WATCH NOW", font=cta_font, fill="white")

    img.save(output_path, quality=95)
    return output_path
