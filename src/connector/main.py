"""Main entry point for the SharePoint connector application."""

from typing import Literal

from connector import utils
from connector.config import (
    MovementPlan,
    MovementPlanDict,
    S3Bucket,
    SecretConfig,
    SharePointLibrary,
)
from connector.engine import UploadToS3Engine, UploadToSharePointEngine

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

    Authenticates to Azure Graph API and validates all configuration at construction
    time. The returned engine can then be used to transfer individual files via
    ``engine.run(source, destination)``.

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

    """
    if mode not in MODE_MAP:
        err = f"Invalid mode '{mode}'. Valid modes: {list(MODE_MAP)}"
        raise ValueError(err)

    secrets = SecretConfig()  # type: ignore[call-arg]
    library = SharePointLibrary(site=sp_site, library=sp_library)
    bucket = S3Bucket(bucket=s3_bucket)

    log.info("Creating engine for mode: %s", mode)

    engine_class = MODE_MAP[mode]
    return engine_class(secrets=secrets, library=library, bucket=bucket)


def create_movement_plan(
    data_movement_plan: list[MovementPlanDict],
) -> list[MovementPlan]:
    """Convert a list of movement plan dicts into validated ``MovementPlan`` objects.

    Each dict must contain ``source`` and ``destination`` string keys. In
    ``write_to_s3`` mode, ``source`` is a SharePoint file path and ``destination``
    is an S3 key. In ``write_to_sharepoint`` mode the roles are reversed.

    Args:
        data_movement_plan (list[MovementPlanDict]):
            A list of ``{"source": str, "destination": str}`` dicts describing
            the files to transfer.

    Returns:
        list[MovementPlan]:
            A list of validated ``MovementPlan`` instances.

    Raises:
        ValidationError: If any dict is missing required fields.

    Example::

        data_movement_plan = [
            {
                "source": "reports/2026/daily_report.csv",
                "destination": "path/to/daily_report.csv",
            }
        ]

    """
    return [
        MovementPlan(source=plan["source"], destination=plan["destination"])
        for plan in data_movement_plan
    ]
