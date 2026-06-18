from pathlib import Path
from core.asset_registry import register_asset
from core.config_loader import load_config

config = load_config()

INBOX_DIR = Path(config["paths"]["assets"]) / "inbox"

IMAGE_EXTENSIONS = set(config["watcher"].get("image_extensions", [
    ".jpg", ".jpeg", ".png", ".webp", ".bmp"
]))

VIDEO_EXTENSIONS = set(config["watcher"].get("video_extensions", [
    ".mp4", ".webm", ".mov", ".mkv"
]))

ALL_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS


def scan_inbox():
    if not INBOX_DIR.exists():
        print(f"Inbox-Ordner nicht gefunden: {INBOX_DIR}")
        return

    count_images = 0
    count_videos = 0
    count_skipped = 0

    print(f"Scanne: {INBOX_DIR}\n")

    for file_path in sorted(INBOX_DIR.iterdir()):
        if not file_path.is_file():
            continue

        ext = file_path.suffix.lower()

        if ext in IMAGE_EXTENSIONS:
            asset_type = "image"
        elif ext in VIDEO_EXTENSIONS:
            asset_type = "video"
        else:
            continue

        result = register_asset(str(file_path), asset_type)

        if result:
            if asset_type == "image":
                count_images += 1
                print(f"  [IMG] {file_path.name}")
            else:
                count_videos += 1
                print(f"  [VID] {file_path.name}")
        else:
            count_skipped += 1

    print(f"\nErgebnis: {count_images} Bilder, {count_videos} Videos registriert, {count_skipped} übersprungen.")


if __name__ == "__main__":
    scan_inbox()
