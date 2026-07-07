from pathlib import Path
import shutil
import json
import html as html_lib
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
    images_dir = (
        release_dir / "images"
    )
    thumbs_dir.mkdir(
        parents=True,
        exist_ok=True
    )
    images_dir.mkdir(
        parents=True,
        exist_ok=True
    )
    html = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "<meta charset='utf-8'>",
        f"<title>Release {release_id}</title>",
        "<style>",
        "body {",
        "    font-family: Arial, sans-serif;",
        "    background: #f0f0f0;",
        "    margin: 20px;",
        "}",
        "h1 {",
        "    text-align: center;",
        "}",
        ".gallery {",
        "    display: grid;",
        "    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));",
        "    gap: 20px;",
        "}",
        ".card {",
        "    background: white;",
        "    border-radius: 10px;",
        "    overflow: hidden;",
        "    box-shadow: 0 2px 6px rgba(0,0,0,0.2);",
        "}",
        ".card img {",
        "    width: 100%;",
        "    display: block;",
        "}",
        ".card p {",
        "    padding: 10px;",
        "    margin: 0;",
        "    text-align: center;",
        "}",
        ".card .description {",
        "    text-align: left;",
        "    font-size: 0.85em;",
        "    color: #444;",
        "    padding-top: 0;",
        "}",
        ".card .tags {",
        "    padding: 0 10px 10px;",
        "    text-align: left;",
        "}",
        ".tag {",
        "    display: inline-block;",
        "    background: #eee;",
        "    border-radius: 12px;",
        "    padding: 2px 8px;",
        "    margin: 2px 2px 0 0;",
        "    font-size: 0.75em;",
        "    color: #555;",
        "}",
        "</style>",
        "</head>",
        "<body>",
        f"<h1>Release {release_id}</h1>",
        "<div class='gallery'>"
    ]
    release_info = {
            "release_id": release_id,
            "asset_count": len(assets),
            "status": "READY",
            "generator": "GalleryForge",
            "assets": []
        }
    for asset in assets:
        asset_id = asset[0]
        filename = asset[1]
        filepath = asset[2]
        thumbnail_path = asset[3]
        description = asset[4] or ""
        tags_raw = asset[5] or ""

        tag_list = [t.strip() for t in tags_raw.split(",") if t.strip()]

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
        image_source = Path(filepath)
        image_target = (
            images_dir /
            image_source.name
        )
        shutil.copy2(
            image_source,
            image_target
        )
        release_info["assets"].append(
                    {
                        "id": asset_id,
                        "filename": filename,
                        "thumbnail": f"thumbnails/{thumb_source.name}",
                        "image": f"images/{image_source.name}",
                        "description": description,
                        "tags": tag_list
                    }
                )

        tags_html = "".join(
            f'<span class="tag">{html_lib.escape(tag)}</span>'
            for tag in tag_list
        )

        html.append(
            f"""
            <div class="card">
                <a href="images/{image_source.name}">
                    <img src="thumbnails/{thumb_source.name}">
                </a>
                <p>{html_lib.escape(filename)}</p>
                <p class="description">{html_lib.escape(description)}</p>
                <div class="tags">{tags_html}</div>
            </div>
            """
        )
    html.extend([
        "</div>",
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
    json_file = (
        release_dir / "release.json"
    )
    json_file.write_text(
        json.dumps(
            release_info,
            indent=4
        ),
        encoding="utf-8"
    )
    print(
        f"Gallery created: {html_file}"
    )


if __name__ == "__main__":
    build_gallery(
        create_release_id()
    )
