"""Main entry point for the SharePoint connector application."""

from typing import Literal

from connector import utils
from connector.config import (
    S3Bucket,
    SecretConfig,
    SharePointLibrary,
)
from connector.engine import UploadToS3Engine, UploadToSharePointEngine
from connector.exceptions import InvalidModeError

log = utils.setup_logger()


MODE_MAP: dict[str, type[UploadToS3Engine | UploadToSharePointEngine]] = {
    "write_to_s3": UploadToS3Engine,
    "write_to_sharepoint": UploadToSharePointEngine,
}


def create_engine(
    mode: Literal["write_to_s3", "write_to_sharepoint"],
    sp_site: str,
    sp_library: str,
    s3_bucket: str,
) -> UploadToSharePointEngine | UploadToS3Engine:
    """Create an engine instance for transferring files between S3 and SharePoint.

    Available engines are ``UploadToS3Engine`` and ``UploadToSharePointEngine``.
    Each is configured with the same SharePoint site, SharePoint library, and S3 bucket.
    The engine will parse one as the source and one as the destination.

    Make use of the 'list_source_files' method to what files are located in the source
    and amend according to your needs.

    Iterate over each file to be transferred and call the 'run' method with the
    source and destination paths to perform the transfer. An s3 source/destination is
    the full s3 key (excluding the bucket name) and a SharePoint source/destination is
    the full path to the file (excluding the site and library).

    The 'run' method validates that the configuration is correct (expected bucket,
    folders and files exist). Then downloads the file from the source and uploads it to
    the destination.

    Optionally delete the source files after successfully transferring them by using
    the optional 'delete' argument in the 'run' method.

    Args:
        mode (Literal["write_to_s3", "write_to_sharepoint"]): Transfer direction.
            ``write_to_s3`` downloads from SharePoint and uploads to S3;
            ``write_to_sharepoint`` downloads from S3 and uploads to SharePoint.
        sp_site (str): SharePoint site name (without the full URL prefix).
            For a file at ``https://justiceuk.sharepoint.com/sites/analytics-site/...``
            use ``sp_site='analytics-site'``.
        sp_library (str): Name of SharePoint document library (e.g. ``'Documents'``).
        s3_bucket (str): S3 bucket name without the ``s3://`` prefix.

    Returns:
        UploadToSharePointEngine | UploadToS3Engine:
            A configured engine instance ready to run file transfers.

    Raises:
        ValueError: If ``mode`` is not one of the valid transfer directions.
        ValidationError: If any configuration value fails Pydantic validation.

    Example:
        >>> eng = create_engine(
        ...     mode="write_to_s3",
        ...     sp_site="analytics-site",
        ...     sp_library="Documents",
        ...     s3_bucket="my-destination-bucket",
        ... )
        >>> eng.run(source="reports/2026/file1.csv", destination="path/to/file1.csv")

    """
    if mode not in MODE_MAP:
        err = f"Invalid mode '{mode}'. Valid modes: {list(MODE_MAP)}"
        raise InvalidModeError(err)

    secrets = SecretConfig()  # type: ignore[call-arg]
    library = SharePointLibrary(site=sp_site, library=sp_library)
    bucket = S3Bucket(bucket=s3_bucket)

    log.info("Creating engine for mode: %s", mode)

    engine_class = MODE_MAP[mode]
    return engine_class(secrets=secrets, library=library, bucket=bucket)
