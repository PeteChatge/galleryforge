from pathlib import Path

from core.asset_registry import register_asset


INBOX_DIR = Path(
    "/mnt/d/___memubot/assets/inbox"
)


IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp"
}


def scan_inbox():

    count = 0

    for file_path in INBOX_DIR.iterdir():

        if not file_path.is_file():
            continue

        extension = file_path.suffix.lower()

        if extension not in IMAGE_EXTENSIONS:
            continue

        if register_asset(
            str(file_path),
            "image"
        ):
            count += 1

    print()
    print(
        f"Registered {count} new assets."
    )


if __name__ == "__main__":
    scan_inbox()
