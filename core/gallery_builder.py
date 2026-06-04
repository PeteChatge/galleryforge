from pathlib import Path
import shutil

from core.release_manager import (
    create_release_id,
    get_release_assets
)


RELEASES_DIR = Path(
    "/mnt/d/___memubot/releases"
)


def build_gallery(release_id):

    assets = get_release_assets(release_id)

    if not assets:
        print(
            f"No assets found for {release_id}"
        )
        return

    release_dir = (
        RELEASES_DIR / release_id
    )

    thumbs_dir = (
        release_dir / "thumbnails"
    )

    thumbs_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    html = [
        "<html>",
        "<body>",
        f"<h1>Release {release_id}</h1>"
    ]

    for asset in assets:

        asset_id = asset[0]
        filename = asset[1]
        filepath = asset[2]
        thumbnail_path = asset[3]

        thumb_source = Path(
            thumbnail_path
        )

        thumb_target = (
            thumbs_dir /
            thumb_source.name
        )

        shutil.copy2(
            thumb_source,
            thumb_target
        )

        html.append(
            f"<div><img src='thumbnails/{thumb_source.name}'></div>"
        )

    html.extend([
        "</body>",
        "</html>"
    ])

    html_file = (
        release_dir / "index.html"
    )

    html_file.write_text(
        "\n".join(html),
        encoding="utf-8"
    )

    print(
        f"Gallery created: {html_file}"
    )


if __name__ == "__main__":

    build_gallery(
        create_release_id()
    )
