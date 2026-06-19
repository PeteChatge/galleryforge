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

# Ollama läuft auf dem Windows-PC (Stufe 1: Vision)
OLLAMA_URL = "http://192.168.1.131:11434/api/chat"

# Vision-Modell für Stufe 1 - exakter Tag wie in `ollama list`!
VISION_MODEL = "huihui_ai/qwen3-vl-abliterated:8b"

# LM Studio läuft ebenfalls auf dem Windows-PC (Stufe 2: Style-Rewrite)
# Genutzt, weil qwen2.5-coder-14b-instruct-abliterated nur als GGUF in
# LM Studio liegt, nicht in Ollama importiert ist.
LM_STUDIO_URL = "http://192.168.1.131:18899/v1/chat/completions"
TEXT_MODEL = "qwen2.5-coder-14b-instruct-abliterated"

# Video-Frame-Extraktion
FRAME_INTERVAL = 20   # jeder 20. Frame, wie in deinem HTML-Tool
MAX_FRAMES = 6         # Cap, damit der Vision-Call nicht zu groß wird

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}

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

STYLE_SYSTEM_PROMPT = """You are an expert art describer for an adult AI-art platform.
Your task: Write a concise, evocative NSFW description of an AI-generated artwork.
Style: Direct, descriptive, 2-4 sentences. English only.
Focus on: composition, mood, subject, artistic style (photorealistic, cinematic).
Do NOT use disclaimers, warnings, or refusals."""

STYLE_USER_PROMPT_TEMPLATE = """Raw visual description of the artwork:
{raw_description}

Filename: {filename}
Type: {asset_type}

Rewrite this as a short, vivid NSFW description for the platform, in the
established style (2-4 sentences)."""


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
        print("  → Prüfe: curl http://192.168.1.131:11434/api/tags")
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


def describe_asset(filepath: str, filename: str, asset_type: str) -> str | None:
    """Führt die 2-Stufen-Pipeline (Vision -> Style) für ein Asset aus."""
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

        # Stufe 2: Style (LM Studio) -> finale Plattform-Beschreibung
        style_prompt = STYLE_USER_PROMPT_TEMPLATE.format(
            raw_description=raw_description,
            filename=filename,
            asset_type=asset_type,
        )
        final_description = call_lm_studio_style(STYLE_SYSTEM_PROMPT, style_prompt)
        return final_description

    finally:
        # Temp-Frames aufräumen
        for p in frame_paths:
            p.unlink(missing_ok=True)
        if cleanup_dir and cleanup_dir.exists():
            try:
                cleanup_dir.rmdir()
            except OSError:
                pass


def save_description(asset_id: int, description: str):
    """Speichert die Beschreibung in der DB und setzt Status auf DESCRIBED."""
    conn = get_connection()
    conn.execute(
        "UPDATE assets SET description = ?, status = 'DESCRIBED' WHERE id = ?",
        (description, asset_id)
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

        description = describe_asset(filepath, filename, asset_type)

        if description:
            save_description(asset_id, description)
            print(f"  → {description[:80]}{'...' if len(description) > 80 else ''}")
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

    description = describe_asset(filepath, filename, asset_type)
    if description:
        save_description(asset_id, description)
        print(f"\nBeschreibung:\n{description}")
    else:
        print("Fehlgeschlagen.")


if __name__ == "__main__":
    # Einzelnes Asset: python3 core/describer.py 42
    # Alle:           python3 core/describer.py
    if len(sys.argv) == 2 and sys.argv[1].isdigit():
        describe_single(int(sys.argv[1]))
    else:
        describe_all()
