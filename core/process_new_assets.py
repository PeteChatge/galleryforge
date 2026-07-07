from pathlib import Path
from core.asset_registry import (
    get_new_assets,
    update_thumbnail
)
from core.thumbnailer import (
    create_thumbnail,
    create_video_thumbnail
)
from core.video_finisher import replace_with_finished
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
        asset_type = asset[3]
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
        if asset_type == "image":
        
            create_thumbnail(
                source_path,
                thumbnail_path
            )
        
        elif asset_type == "video":

            try:
                finished = replace_with_finished(
                    asset_id,
                    str(source_path)
                )
                if not finished:
                    print(
                        f"  Veredelung fehlgeschlagen, nutze Original: {filename}"
                    )
            except Exception as e:
                print(
                    f"  Veredelung-FEHLER ({type(e).__name__}: {e}), nutze Original: {filename}"
                )

            create_video_thumbnail(
                source_path,
                thumbnail_path
            )
        
        else:
        
            print(
                f"Unsupported asset type: {asset_type}"
            )
        
            continue
            
        update_thumbnail(
            asset_id,
            str(thumbnail_path)
        )
        print(
            f"Processed: {filename}"
        )
if __name__ == "__main__":
    process_new_assets()
