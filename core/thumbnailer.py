from pathlib import Path
from PIL import Image
import subprocess


THUMBNAIL_SIZE = (512, 512)


def create_thumbnail(
    source_path,
    target_path
):

    source_path = Path(source_path)
    target_path = Path(target_path)

    target_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with Image.open(source_path) as img:

        img.thumbnail(
            THUMBNAIL_SIZE
        )

        img.save(
            target_path,
            format="WEBP",
            quality=90
        )

    return str(target_path)


def create_video_thumbnail(
    source_path,
    target_path
):

    source_path = Path(source_path)
    target_path = Path(target_path)

    target_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    temp_file = (
        target_path.parent /
        f"{target_path.stem}_temp.jpg"
    )

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            "1",
            "-i",
            str(source_path),
            "-frames:v",
            "1",
            str(temp_file)
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True
    )

    with Image.open(temp_file) as img:

        img.thumbnail(
            THUMBNAIL_SIZE
        )

        img.save(
            target_path,
            format="WEBP",
            quality=90
        )

    temp_file.unlink(
        missing_ok=True
    )

    return str(target_path)


if __name__ == "__main__":

    create_thumbnail(
        "/mnt/d/___memubot/assets/inbox/test.png",
        "/mnt/d/___memubot/assets/thumbnails/test.webp"
    )

    print("Thumbnail created.")
