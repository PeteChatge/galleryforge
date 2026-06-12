from pathlib import Path
import json

from core.release_manager import (
    create_release_id
)


RELEASES_DIR = Path(
    "/mnt/d/___memubot/releases"
)


def load_release(release_id):

    release_file = (
        RELEASES_DIR /
        release_id /
        "release.json"
    )

    if not release_file.exists():

        raise FileNotFoundError(
            f"Release not found: {release_file}"
        )

    return json.loads(
        release_file.read_text(
            encoding="utf-8"
        )
    )


def detect_asset_type(filename):

    suffix = (
        Path(filename)
        .suffix
        .lower()
    )

    if suffix in [
        ".png",
        ".jpg",
        ".jpeg",
        ".webp"
    ]:
        return "image"

    if suffix in [
        ".mp4",
        ".mov",
        ".mkv",
        ".webm"
    ]:
        return "video"

    return "unknown"


def build_payload(release_data):

    payload = {
        "release": release_data[
            "release_id"
        ],
        "asset_count": release_data[
            "asset_count"
        ],
        "items": []
    }

    for asset in release_data[
        "assets"
    ]:

        payload["items"].append(
            {
                "id": asset["id"],
                "filename": asset[
                    "filename"
                ],
                "type": detect_asset_type(
                    asset["filename"]
                ),
                "thumbnail": asset[
                    "thumbnail"
                ],
                "image": asset[
                    "image"
                ]
            }
        )

    return payload


def dry_run():

    release_id = (
        create_release_id()
    )

    release_data = load_release(
        release_id
    )

    payload = build_payload(
        release_data
    )

    print()

    print(
        json.dumps(
            payload,
            indent=4
        )
    )

    print()


if __name__ == "__main__":

    dry_run()
