from pathlib import Path

from PIL import Image

THUMBNAIL_SIZE = (512, 512)


def create_thumbnail(source_path, target_path):

    source_path = Path(source_path)
    target_path = Path(target_path)

    target_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with Image.open(source_path) as img:

        img.thumbnail(THUMBNAIL_SIZE)

        img.save(
            target_path,
            format="WEBP",
            quality=90
        )

    return str(target_path)

if __name__ == "__main__":

    create_thumbnail(
        "/mnt/d/___memubot/assets/inbox/test.png",
        "/mnt/d/___memubot/assets/thumbnails/test.webp"
    )

    print("Thumbnail created.")
