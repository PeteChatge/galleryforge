#!/usr/bin/env python3
"""
GalleryForge - Describer
Generiert NSFW-Beschreibungen für Assets via Ollama (2-Stufen-Pipeline).
Verarbeitet alle Assets mit Status 'NEW' oder 'THUMBNAILED'.

Pipeline:
  Stufe 1 (Vision):  qwen2.5vl schaut sich das Bild / die Video-Frames
                      tatsächlich an -> sachliche Rohbeschreibung.
  Stufe 2 (Style):    qwen2.5-coder-14b-instruct-abliterated schreibt die
                      Rohbeschreibung im etablierten NSFW-Plattform-Stil um.

Videos werden per ffmpeg in Einzelframes zerlegt (jeder N-te Frame, wie
dein HTML-Frame-Extractor) und alle Frames in EINEM Vision-Call analysiert.

Speichern als: core/describer.py
Ausführen:     python3 -m core.describer
               oder: python3 core/describer.py
"""

import sys
import base64
import subprocess
import tempfile
from pathlib import Path

import requests

from core.database import get_connection
from core.asset_registry import get_assets_by_status

# Endpunkte/Modelle kommen aus config/app.yaml (describer:), mit Fallbacks.
# Stufe 1 (Vision): Ollama mit Vision-Modell (Original-Rezept:
# huihui_ai/qwen3-vl-abliterated:8b). Stufe 2 (Style+Tags): zuerst LM Studio,
# bei Ausfall automatisch Ollama-Fallback mit abliteriertem Text-Modell.
try:
    from core.config_loader import load_config as _load_cfg

    _cfg = _load_cfg() or {}
except Exception:
    _cfg = {}
_d = (_cfg.get("describer") or {})

# Ollama (Stufe 1: Vision + Stufe-2-Fallback)
OLLAMA_URL = _d.get("ollama_url", "http://127.0.0.1:11434/api/chat")

# Vision-Modell für Stufe 1 - exakter Tag wie in `ollama list`!
VISION_MODEL = _d.get("vision_model", "huihui_ai/qwen3-vl-abliterated:8b")

# LM Studio (Stufe 2: Style-Rewrite, Text only)
LM_STUDIO_URL = _d.get(
    "lm_studio_url", "http://127.0.0.1:18899/v1/chat/completions"
)
TEXT_MODEL = _d.get("text_model", "qwen2.5-coder-14b-instruct-abliterated")

# Ollama-Fallback für Stufe 2, wenn LM Studio aus ist (abliteriert!).
TEXT_FALLBACK_MODEL = _d.get("text_fallback_model", "qwen35-huihui:latest")

# Video-Frame-Extraktion
FRAME_INTERVAL = 20   # jeder 20. Frame, wie in deinem HTML-Tool
MAX_FRAMES = 6         # Cap, damit der Vision-Call nicht zu groß wird

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}

# Dein Artist-Tag - wird bei JEDEM Asset automatisch gesetzt, unabhängig vom Inhalt
BRAND_TAGS = ["rembrandtius"]

# Vokabular, aus dem das Modell passende Tags auswählt (Niche-Begriffe).
# Liste einfach erweitern, wenn dir neue Begriffe einfallen.
TAG_VOCABULARY = [
    "strongwoman", "femalebeatsmale", "femdom", "bigmusclewoman",
    "musclemistress", "thickthighs", "largecalves", "calflover",
    "muscularlegs", "massivewoman", "femalemuscle", "ottilieremmes",
    "bigmusclegirl", "femalemusclethickness", "chubbymusclewoman",
    "muscularbbw",
]

VISION_SYSTEM_PROMPT = """You are a visual analysis assistant. Describe exactly
what is visible in the image(s) provided: subjects, poses, clothing or nudity,
setting, lighting, camera angle, and art style (photorealistic, cinematic, etc).
Be specific and factual, 4-6 sentences. No moral commentary, no disclaimers,
no refusals."""

VISION_USER_PROMPT_IMAGE = "Describe exactly what you see in this image."

VISION_USER_PROMPT_VIDEO = (
    "These are {n} sequential frames sampled from a short video clip, in order. "
    "Describe what happens across the frames: subjects, actions/motion, setting, "
    "and art style."
)

STYLE_SYSTEM_PROMPT = """You are an expert art describer and tagger for an adult \
AI-art platform (female-muscle / femdom niche).
You will be given a raw factual description of an AI-generated artwork.

Your job has two parts:

1. DESCRIPTION: Rewrite the raw description as a concise, evocative NSFW \
description. Style: direct, descriptive, 2-4 sentences. English only. Focus on \
composition, mood, subject, artistic style (photorealistic, cinematic). No \
disclaimers, warnings, or refusals.

2. TAGS: From this niche tag vocabulary, select every tag that genuinely fits \
what is described - do not force tags that don't apply:
{tag_vocabulary}
You may add up to 2 additional single-word, lowercase tags (no spaces) if \
something clearly relevant isn't covered by the vocabulary above. Order tags \
from most to least specific/relevant.

Output EXACTLY in this format, nothing else, no extra commentary:
DESCRIPTION: <description text>
TAGS: <comma-separated tags>"""

STYLE_USER_PROMPT_TEMPLATE = """Raw visual description of the artwork:
{raw_description}

Filename: {filename}
Type: {asset_type}"""


def is_video(filepath: str) -> bool:
    return Path(filepath).suffix.lower() in VIDEO_EXTENSIONS


def encode_image_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8")


def extract_video_frames(filepath: str, interval: int = FRAME_INTERVAL,
                          max_frames: int = MAX_FRAMES) -> list[Path]:
    """Extrahiert per ffmpeg jeden N-ten Frame in ein Temp-Verzeichnis."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="gf_frames_"))
    pattern = str(tmp_dir / "frame_%03d.jpg")

    cmd = [
        "ffmpeg", "-y", "-i", filepath,
        "-vf", f"select=not(mod(n\\,{interval}))",
        "-vsync", "vfr",
        "-vframes", str(max_frames),
        pattern,
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=120)
    except FileNotFoundError:
        print("  FEHLER: ffmpeg nicht gefunden. Installieren mit: sudo apt install ffmpeg")
        return []
    except subprocess.CalledProcessError as e:
        print(f"  FEHLER: ffmpeg-Frame-Extraktion fehlgeschlagen: {e.stderr.decode(errors='ignore')[:200]}")
        return []
    except subprocess.TimeoutExpired:
        print("  FEHLER: ffmpeg-Frame-Extraktion Timeout.")
        return []

    return sorted(tmp_dir.glob("frame_*.jpg"))


def parse_style_response(text: str) -> tuple[str, list[str]]:
    """Zerlegt die LM-Studio-Antwort in (description, tags)."""
    description = text.strip()
    tags: list[str] = []

    if "TAGS:" in text:
        desc_part, tags_part = text.split("TAGS:", 1)
        description = desc_part.replace("DESCRIPTION:", "").strip()
        tags = [t.strip().lower() for t in tags_part.split(",") if t.strip()]
    else:
        description = text.replace("DESCRIPTION:", "").strip()

    return description, tags


def merge_tags(model_tags: list[str]) -> list[str]:
    """Brand-Tags voranstellen, Duplikate entfernen, Reihenfolge erhalten."""
    seen = set()
    result = []
    for tag in BRAND_TAGS + model_tags:
        key = tag.lower().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result


def call_ollama_vision(system_prompt: str, user_content: str,
                        images_b64: list[str]) -> str | None:
    """Ollama /api/chat Call mit Bildern (Stufe 1: Vision)."""
    user_message = {"role": "user", "content": user_content, "images": images_b64}

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": VISION_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    user_message,
                ],
                "stream": False,
                "options": {"temperature": 0.7},
                "keep_alive": 0,  # sofort entladen -> VRAM frei für LM Studio
            },
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"].strip()

    except requests.exceptions.ConnectionError:
        print(f"  FEHLER: Ollama nicht erreichbar unter {OLLAMA_URL}")
        print("  → Prüfe: curl http://127.0.0.1:11434/api/tags")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"  FEHLER: Ollama {e.response.status_code}: {e.response.text[:200]}")
        print(f"  → Prüfe ob '{VISION_MODEL}' exakt so in 'ollama list' steht.")
        return None
    except requests.exceptions.Timeout:
        print(f"  FEHLER: Timeout – Modell '{VISION_MODEL}' antwortet zu langsam.")
        return None
    except Exception as e:
        print(f"  FEHLER: {type(e).__name__}: {e}")
        return None


def call_lm_studio_style(system_prompt: str, user_content: str) -> str | None:
    """LM Studio /v1/chat/completions Call (Stufe 2: Style-Rewrite, Text only)."""
    try:
        response = requests.post(
            LM_STUDIO_URL,
            json={
                "model": TEXT_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.7,
                "max_tokens": 500,
            },
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    except requests.exceptions.ConnectionError:
        print(f"  FEHLER: LM Studio nicht erreichbar unter {LM_STUDIO_URL}")
        return None
    except requests.exceptions.HTTPError as e:
        print(f"  FEHLER: LM Studio {e.response.status_code}: {e.response.text[:200]}")
        print(f"  → Prüfe ob '{TEXT_MODEL}' in LM Studio geladen ist.")
        return None
    except requests.exceptions.Timeout:
        print(f"  FEHLER: Timeout – Modell '{TEXT_MODEL}' antwortet zu langsam.")
        return None
    except Exception as e:
        print(f"  FEHLER: {type(e).__name__}: {e}")
        return None


def call_ollama_text(system_prompt: str, user_content: str) -> str | None:
    """Ollama /api/chat Call ohne Bilder (Stufe-2-Fallback, Text only)."""
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": TEXT_FALLBACK_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "stream": False,
                "options": {"temperature": 0.7},
                "keep_alive": 0,  # sofort entladen -> VRAM frei
            },
            timeout=300,
        )
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"].strip()

    except requests.exceptions.ConnectionError:
        print(f"  FEHLER: Ollama nicht erreichbar unter {OLLAMA_URL}")
        return None
    except Exception as e:
        print(f"  FEHLER: Ollama-Fallback {type(e).__name__}: {e}")
        return None


def style_rewrite(system_prompt: str, user_content: str) -> str | None:
    """Stufe 2 mit Fallback-Kette: LM Studio -> Ollama (abliteriert)."""
    raw_response = call_lm_studio_style(system_prompt, user_content)
    if raw_response:
        return raw_response
    print(f"  → LM Studio aus, Fallback: Ollama '{TEXT_FALLBACK_MODEL}' ...")
    return call_ollama_text(system_prompt, user_content)


def describe_asset(filepath: str, filename: str, asset_type: str) -> tuple[str, list[str]] | None:
    """Führt die 2-Stufen-Pipeline (Vision -> Style+Tags) für ein Asset aus."""
    frame_paths: list[Path] = []
    cleanup_dir: Path | None = None

    try:
        if is_video(filepath):
            frame_paths = extract_video_frames(filepath)
            if not frame_paths:
                print("  → Keine Frames extrahiert, überspringe.")
                return None
            cleanup_dir = frame_paths[0].parent
            images_b64 = [encode_image_b64(p) for p in frame_paths]
            vision_prompt = VISION_USER_PROMPT_VIDEO.format(n=len(frame_paths))
        else:
            src = Path(filepath)
            if not src.exists():
                print(f"  FEHLER: Datei nicht gefunden: {filepath}")
                return None
            images_b64 = [encode_image_b64(src)]
            vision_prompt = VISION_USER_PROMPT_IMAGE

        # Stufe 1: Vision (Ollama) -> Rohbeschreibung
        raw_description = call_ollama_vision(
            VISION_SYSTEM_PROMPT, vision_prompt, images_b64
        )
        if not raw_description:
            return None

        # Stufe 2: Style + Tags (LM Studio, Fallback Ollama) -> Beschreibung + Tags
        style_system = STYLE_SYSTEM_PROMPT.format(
            tag_vocabulary=", ".join(TAG_VOCABULARY)
        )
        style_prompt = STYLE_USER_PROMPT_TEMPLATE.format(
            raw_description=raw_description,
            filename=filename,
            asset_type=asset_type,
        )
        raw_response = style_rewrite(style_system, style_prompt)
        if not raw_response:
            return None

        description, model_tags = parse_style_response(raw_response)
        tags = merge_tags(model_tags)
        return description, tags

    finally:
        # Temp-Frames aufräumen
        for p in frame_paths:
            p.unlink(missing_ok=True)
        if cleanup_dir and cleanup_dir.exists():
            try:
                cleanup_dir.rmdir()
            except OSError:
                pass


def save_result(asset_id: int, description: str, tags: list[str]):
    """Speichert Beschreibung + Tags in der DB und setzt Status auf DESCRIBED."""
    conn = get_connection()
    conn.execute(
        "UPDATE assets SET description = ?, tags = ?, status = 'DESCRIBED' WHERE id = ?",
        (description, ", ".join(tags), asset_id)
    )
    conn.commit()
    conn.close()


def describe_all(statuses: list[str] = None):
    """
    Beschreibt alle Assets mit den angegebenen Status-Werten.
    Standard: NEW und THUMBNAILED
    """
    if statuses is None:
        statuses = ["NEW", "THUMBNAILED"]

    assets = []
    for status in statuses:
        assets.extend(get_assets_by_status(status))

    if not assets:
        print("Keine Assets zum Beschreiben gefunden.")
        return

    print(f"Zu beschreiben: {len(assets)} Assets\n")

    success = 0
    failed = 0

    for asset in assets:
        asset_id, filename, filepath, asset_type, status = asset

        print(f"[{asset_id}] {filename} ({asset_type})")

        result = describe_asset(filepath, filename, asset_type)

        if result:
            description, tags = result
            save_result(asset_id, description, tags)
            print(f"  → {description[:80]}{'...' if len(description) > 80 else ''}")
            print(f"  Tags: {', '.join(tags)}")
            success += 1
        else:
            failed += 1
            print("  → Übersprungen.")

        print()

    print(f"Ergebnis: {success} beschrieben, {failed} fehlgeschlagen.")


def describe_single(asset_id: int):
    """Beschreibt ein einzelnes Asset anhand seiner ID."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, filename, filepath, asset_type, status FROM assets WHERE id = ?",
        (asset_id,)
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        print(f"Asset ID {asset_id} nicht gefunden.")
        return

    asset_id, filename, filepath, asset_type, status = row
    print(f"Beschreibe: [{asset_id}] {filename}")

    description_result = describe_asset(filepath, filename, asset_type)
    if description_result:
        description, tags = description_result
        save_result(asset_id, description, tags)
        print(f"\nBeschreibung:\n{description}")
        print(f"\nTags:\n{', '.join(tags)}")
    else:
        print("Fehlgeschlagen.")


if __name__ == "__main__":
    # Einzelnes Asset: python3 core/describer.py 42
    # Alle:           python3 core/describer.py
    if len(sys.argv) == 2 and sys.argv[1].isdigit():
        describe_single(int(sys.argv[1]))
    else:
        describe_all()
