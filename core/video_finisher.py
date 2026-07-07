#!/usr/bin/env python3
"""
GalleryForge - Video Finisher
Schickt ein WAN-Kaskaden-Segment durch die ComfyUI-Veredelungskette
(Upscale -> Filter -> RIFE -> Film Grain) und ersetzt die Original-Datei
mit dem veredelten Ergebnis (kein Zwischenprodukt-Storage).

Speichern als: core/video_finisher.py
Workflow-JSON ablegen als: core/workflows/film_grain_resizer.json
"""

import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import requests

# ComfyUI laeuft auf dem Windows-PC
COMFYUI_URL = "http://192.168.1.131:18188"

# ANNAHME, bitte pruefen: Standard-Output-Ordner der portablen ComfyUI-Installation.
# Falls dein Output-Pfad anders liegt (z.B. eigener output_directory-Parameter beim
# Start), hier anpassen.
COMFYUI_OUTPUT_DIR = Path(
    "/mnt/c/Users/Olaf/Downloads/ComfyUI/ComfyUI_windows_portable/ComfyUI/output"
)

WORKFLOW_TEMPLATE = Path(__file__).parent / "workflows" / "film_grain_resizer.json"

LOADER_NODE_ID = "2"
GRAIN_NODE_ID = "286"
FILENAME_PREFIX = "AnimateDiff"  # muss zum filename_prefix im Workflow-JSON passen


def wsl_to_windows_path(wsl_path: str) -> str:
    """/mnt/d/foo/bar -> D:\\foo\\bar (ComfyUI laeuft nativ auf Windows)."""
    p = Path(wsl_path)
    parts = p.parts
    if len(parts) >= 3 and parts[0] == "/" and parts[1] == "mnt":
        drive = parts[2].upper()
        rest = parts[3:]
        return f"{drive}:\\" + "\\".join(rest)
    return wsl_path  # war wohl schon ein Windows-Pfad


def free_comfyui_memory():
    """Entlaedt Modelle und leert den Cache - verhindert VRAM-Reste zwischen Jobs."""
    try:
        requests.post(
            f"{COMFYUI_URL}/free",
            json={"unload_models": True, "free_memory": True},
            timeout=30,
        )
        time.sleep(5)  # kurz Luft zum Aufraeumen geben
    except requests.exceptions.RequestException as e:
        print(f"  Warnung: /free-Aufruf fehlgeschlagen: {e}")


def finish_video(filepath: str, timeout: int = 2400) -> Path | None:
    """Schickt das Video durch ComfyUI. Gibt den Pfad zur fertigen Datei zurueck
    (liegt noch im ComfyUI-Output-Ordner, noch nicht verschoben)."""
    if not WORKFLOW_TEMPLATE.exists():
        print(f"  FEHLER: Workflow-Template nicht gefunden: {WORKFLOW_TEMPLATE}")
        return None

    workflow = json.loads(WORKFLOW_TEMPLATE.read_text())
    workflow[LOADER_NODE_ID]["inputs"]["video"] = wsl_to_windows_path(filepath)
    # Zufaelliger Seed pro Asset, sonst identisches Grain-Muster bei jedem Lauf
    workflow[GRAIN_NODE_ID]["inputs"]["seed"] = uuid.uuid4().int & 0x7FFFFFFF

    free_comfyui_memory()  # VRAM-Reste vom letzten Job weg, bevor wir neu starten

    client_id = str(uuid.uuid4())
    start_time = time.time()

    try:
        response = requests.post(
            f"{COMFYUI_URL}/prompt",
            json={"prompt": workflow, "client_id": client_id},
            timeout=30,
        )
        response.raise_for_status()
        prompt_id = response.json()["prompt_id"]
    except requests.exceptions.RequestException as e:
        print(f"  FEHLER: ComfyUI nicht erreichbar oder lehnte ab: {e}")
        return None
    except KeyError:
        print(f"  FEHLER: Unerwartete ComfyUI-Antwort: {response.text[:300]}")
        return None

    print(f"  ComfyUI-Job gestartet (prompt_id={prompt_id}), warte auf Fertigstellung...")

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            hist = requests.get(f"{COMFYUI_URL}/history/{prompt_id}", timeout=10).json()
        except requests.exceptions.RequestException:
            time.sleep(3)
            continue

        if prompt_id in hist:
            status = hist[prompt_id].get("status", {})
            if status.get("completed"):
                break
            if status.get("status_str") == "error":
                print(f"  FEHLER: ComfyUI meldet Fehler im Workflow: {status}")
                free_comfyui_memory()
                return None
        time.sleep(3)
    else:
        print(f"  FEHLER: Timeout nach {timeout}s - ComfyUI-Job nicht fertig geworden.")
        free_comfyui_memory()
        return None

    free_comfyui_memory()  # aufraeumen, bevor der naechste Job (falls einer folgt) startet

    # Fertige Datei ueber das Dateisystem finden (robuster als das Output-JSON-
    # Schema von VHS_VideoCombine zu parsen, das je nach Version variieren kann)
    candidates = sorted(
        COMFYUI_OUTPUT_DIR.glob(f"{FILENAME_PREFIX}*.mp4"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for candidate in candidates:
        if candidate.stat().st_mtime >= start_time:
            return candidate

    print("  FEHLER: Keine neue Output-Datei im ComfyUI-Output-Ordner gefunden.")
    return None


def probe_video_metadata(filepath: str) -> dict:
    """Liest width/height/duration per ffprobe aus der fertigen Datei."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,duration",
             "-of", "json", filepath],
            capture_output=True, text=True, timeout=30, check=True,
        )
        stream = json.loads(result.stdout)["streams"][0]
        return {
            "width": int(stream.get("width", 0)),
            "height": int(stream.get("height", 0)),
            "duration_seconds": float(stream.get("duration", 0)),
        }
    except Exception as e:
        print(f"  Warnung: ffprobe fehlgeschlagen: {e}")
        return {}


def replace_with_finished(asset_id: int, original_filepath: str) -> bool:
    """Veredelt das Video und ueberschreibt die Original-Datei.
    Aktualisiert file_size/width/height/duration_seconds in der DB.
    Gibt True bei Erfolg zurueck."""
    finished_path = finish_video(original_filepath)
    if not finished_path:
        return False

    original = Path(original_filepath)
    shutil.move(str(finished_path), str(original))  # ueberschreibt das Original

    metadata = probe_video_metadata(str(original))
    if metadata:
        from core.database import get_connection
        conn = get_connection()
        conn.execute(
            "UPDATE assets SET file_size = ?, width = ?, height = ?, "
            "duration_seconds = ? WHERE id = ?",
            (original.stat().st_size, metadata.get("width"), metadata.get("height"),
             metadata.get("duration_seconds"), asset_id),
        )
        conn.commit()
        conn.close()

    return True
