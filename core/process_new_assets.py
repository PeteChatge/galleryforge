from pathlib import Path

from core.asset_registry import (
    get_new_assets,
    update_thumbnail
)

from core.thumbnailer import create_thumbnail


THUMBNAIL_DIR = Path(
    "/mnt/d/___memubot/assets/thumbnails"
)


def process_new_assets():

    assets = get_new_assets()

    if not assets:
        print("No NEW assets found.")
        return

    for asset in assets:

        asset_id = asset[0]
        filename = asset[1]
        filepath = asset[2]

        source_path = Path(filepath)

        if not source_path.exists():

            print(
                f"Missing file: {source_path}"
            )

            continue

        thumbnail_path = (
            THUMBNAIL_DIR /
            f"{source_path.stem}.webp"
        )

        create_thumbnail(
            source_path,
            thumbnail_path
        )

        update_thumbnail(
            asset_id,
            str(thumbnail_path)
        )

        print(
            f"Processed: {filename}"
        )

if __name__ == "__main__":
    process_new_assets()
