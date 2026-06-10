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
    """Create an engine instance based on the mode.

    Args:
        mode (Literal["write_to_s3", "write_to_sharepoint"] | None): The mode of
            operation determining the type of engine to create.
        sp_site (str | None): SharePoint site name
        sp_library (str | None): SharePoint library name
        s3_bucket (str | None): S3 bucket name

    For a SharePoint file located at:
    `https://justiceuk.sharepoint.com/sites/analytics-site/Documents/exports/reports/2026/04/daily_report.csv`
    - sp_site = 'analytics-site'
    - sp_library = 'Documents'

    If no arguments are provided, the function will attempt to read values from
    the environment variables "MODE", "SP_LIBRARY", "SP_SITE", and "S3_BUCKET".

    Returns:
        tuple[type[UploadToSharePointEngine | UploadToS3Engine], SecretConfig]:
            A tuple containing the engine class and the secrets configuration.

    Raises:
        ValueError: If an invalid mode is provided.

    """
    secrets = SecretConfig()  # type: ignore[call-arg]
    library = SharePointLibrary(site=sp_site, library=sp_library)
    bucket = S3Bucket(bucket=s3_bucket)

    if mode not in MODE_MAP:
        err = f"Invalid mode '{mode}'. Valid modes: {list(MODE_MAP)}"
        raise ValueError(err)

    log.info("Creating engine for mode: %s", mode)

    engine_class = MODE_MAP[mode]
    return engine_class(secrets=secrets, library=library, bucket=bucket)


def create_movement_plan(
    data_movement_plan: list[MovementPlanDict],
) -> list[MovementPlan]:
    """Create a DataMovementPlan from a list of movement plan dictionaries.

    Args:
        data_movement_plan (list[MovementPlanDict]):
            A list of dictionaries representing the movement plans to be validated and
            converted into a DataMovementPlan instance.

    Returns:
        list[MovementPlan]:
            A list of validated movement plans.

    Raises:
        ValueError: If an invalid mode is provided or if the movement plans are not
            valid according to the specified mode.

    Example movement plan:
    ----------------------

    ```
    data_movement_plan=[
        {
            "source": "reports/2026/daily_report.csv",
            "destination": "path/to/daily_report.csv"
            }
        }
    ]
    ```

    """
    return [
        MovementPlan(source=plan["source"], destination=plan["destination"])
        for plan in data_movement_plan
    ]


# Add checks for whether configs / filepaths are valid and exist
# List file in s3 / SP
# delete / move files
