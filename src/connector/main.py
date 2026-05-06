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

    log.info(
        "Configured transfer mode='%s', s3_bucket='%s', s3_key='%s', "
        "sharepoint_target='%s%s'",
        config.MODE,
        config.S3_BUCKET,
        config.FILE_KEY,
        config.SP_FOLDER_PATH,
        config.SP_FILE_NAME,
    )

    engine_class = ENGINE_MAP[config.MODE]
    engine = engine_class(config=config)

    try:
        content = engine.download_file()
        engine.upload_file(content)
        log.info("File transfer completed successfully.")
    except UploadError:
        log.exception("File transfer failed")
        raise


if __name__ == "__main__":
    main()  # pragma: no cover
