"""Main entry point for the SharePoint connector application."""

from connector.config import AppConfig
from connector.engine import UploadToS3Engine, UploadToSharePointEngine
from connector.exceptions import UploadError
from connector.utils import setup_logger

log = setup_logger()

ENGINE_MAP: dict[str, type[UploadToSharePointEngine | UploadToS3Engine]] = {
    "write_to_s3": UploadToS3Engine,
    "write_to_sharepoint": UploadToSharePointEngine,
}


def main() -> None:
    """Entry point for the connector application."""
    log.info("Starting file transfer process...")
    config = AppConfig()  # type: ignore[call-arg]

    engine_class = ENGINE_MAP[config.MODE]
    if not engine_class:
        err = (
            f"Invalid engine specified: {config.MODE}. Valid options are: "
            f"{', '.join(ENGINE_MAP.keys())}"
        )
        raise ValueError(err)

    engine = engine_class(config=config)
    try:
        content = engine.download_file()
        engine.upload_file(content)
        log.info("File transfer completed successfully.")
    except UploadError as exc:
        err = f"File transfer failed: {exc}"
        raise UploadError(err) from exc


if __name__ == "__main__":
    main()
