from src.config import AppConfig
from src.exceptions import UploadError
from src.utils import setup_logger
from src.engine import UploadToSharePointEngine, UploadToS3Engine

log = setup_logger()

ENGINE_MAP: dict[str, type[UploadToSharePointEngine | UploadToS3Engine]] = {
    "write_to_s3": UploadToS3Engine,
    "write_to_sharepoint": UploadToSharePointEngine,
}


def main():
    log.info("Starting file transfer process...")
    config = AppConfig()

    engine_class = ENGINE_MAP.get(config.MODE)
    if not engine_class:
        raise ValueError(f"Invalid engine specified: {config.MODE}")

    engine = engine_class(config=config)
    try:
        content = engine.download_file()
        engine.upload_file(content)
        log.info("File transfer completed successfully.")
    except UploadError as exc:
        log.error("File transfer failed: %s", exc)


if __name__ == "__main__":
    main()
