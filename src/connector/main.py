"""Main entry point for the SharePoint connector application."""

import os

from connector.config import ConnectorConfig
from connector.engine import UploadToS3Engine, UploadToSharePointEngine
from connector.exceptions import UploadError
from connector.utils import setup_logger

log = setup_logger()

ENGINE_MAP: dict[str, type[UploadToSharePointEngine | UploadToS3Engine]] = {
    "write_to_s3": UploadToS3Engine,
    "write_to_sharepoint": UploadToSharePointEngine,
}


def setup_environment_variables(non_secret_env_vars: dict[str, str]) -> None:
    """Set up environment variables from a dictionary.

    Args:
        non_secret_env_vars (dict[str, str]): Environment variable names and values
        passed by calling code

    Returns:
        None

    """
    for var_name, var_value in non_secret_env_vars.items():
        if var_value is not None:
            os.environ[var_name] = var_value


def main(
    non_secret_env_vars: dict[str, str] | None = None,
) -> None:
    """Entry point for the connector application.

    Args:
        non_secret_env_vars (dict[str, str] | None): Environment variable names and
        values passed by calling code. No secret values should be passed here.

    Returns:
        None

    """
    log.info("Starting file transfer process...")

    if non_secret_env_vars:
        setup_environment_variables(non_secret_env_vars)

    config = ConnectorConfig()  # type: ignore[call-arg]

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
