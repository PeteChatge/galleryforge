import time
from pathlib import Path

from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

from core.config_loader import load_config
from core.logger import setup_logger
from core.asset_registry import register_asset

config = load_config()
logger = setup_logger()

ASSET_PATH = config["paths"]["assets"]

IMAGE_EXTENSIONS = config["watcher"]["image_extensions"]
VIDEO_EXTENSIONS = config["watcher"]["video_extensions"]


class AssetHandler(FileSystemEventHandler):

    def on_created(self, event):

        if event.is_directory:
            return

        file_path = Path(event.src_path)
        extension = file_path.suffix.lower()

        if extension in IMAGE_EXTENSIONS:
            logger.info(f"New image detected: {file_path.name}")

            register_asset(
                str(file_path),
                "image"
            )

        elif extension in VIDEO_EXTENSIONS:
            logger.info(f"New video detected: {file_path.name}")

            register_asset(
                str(file_path),
                "video"
            )

        else:
            logger.info(f"Ignored file: {file_path.name}")

if __name__ == "__main__":

    observer = PollingObserver(timeout=2)

    handler = AssetHandler()

    observer.schedule(
        handler,
        path=ASSET_PATH,
        recursive=config["watcher"]["recursive"]
    )

    observer.start()

    logger.info(f"Watching assets folder: {ASSET_PATH}")

    try:
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        observer.stop()

    observer.join()
