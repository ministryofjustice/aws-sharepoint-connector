"""Main entry point for the SharePoint connector application."""

import os
from typing import Literal, TypedDict

from dotenv import load_dotenv

from connector import config, utils
from connector.engine import UploadToS3Engine, UploadToSharePointEngine

log = utils.setup_logger()


class ModeMapDict(TypedDict):
    """TypedDict for mapping connector modes to movement plans and engines."""

    plan: type[config.S3ToSPMovementPlan | config.SPToS3MovementPlan]
    engine: type[UploadToSharePointEngine | UploadToS3Engine]


MODE_MAP: dict[str, ModeMapDict] = {
    "write_to_s3": {
        "plan": config.SPToS3MovementPlan,
        "engine": UploadToS3Engine,
    },
    "write_to_sharepoint": {
        "plan": config.S3ToSPMovementPlan,
        "engine": UploadToSharePointEngine,
    },
}


def create_engine(
    mode: Literal["write_to_s3", "write_to_sharepoint"],
    sp_library: str,
    sp_site: str,
    s3_bucket: str,
) -> UploadToSharePointEngine | UploadToS3Engine:
    """Create an engine instance based on the mode.

    Args:
        mode (Literal["write_to_s3", "write_to_sharepoint"] | None): The mode of
            operation determining the type of engine to create.
        sp_library (str | None): SharePoint library name for engine creation.
        sp_site (str | None): SharePoint site name for engine creation.
        s3_bucket (str | None): S3 bucket name for engine creation.

    If no arguments are provided, the function will attempt to read values from
    the environment variables "MODE", "SP_LIBRARY", "SP_SITE", and "S3_BUCKET".

    Returns:
        tuple[type[UploadToSharePointEngine | UploadToS3Engine], config.SecretConfig]:
            A tuple containing the engine class and the secrets configuration.

    Raises:
        ValueError: If an invalid mode is provided.

    """
    secrets = config.SecretConfig()  # type: ignore[call-arg]
    library = config.SharePointLibrary(site=sp_site, library=sp_library)
    bucket = config.S3Bucket(bucket=s3_bucket)

    log.info("Creating engine for mode: %s", mode)

    engine_class = MODE_MAP[mode]["engine"]
    return engine_class(secrets=secrets, library=library, bucket=bucket)  # type: ignore[call-arg]


# def create_movement_plan(
#     data_movement_plan: list[config.S3ToSPMPDict] | list[config.SPToS3MPDict],
#     mode: Literal["write_to_s3", "write_to_sharepoint"] | None = None,
# ) -> list[config.S3ToSPMovementPlan] | list[config.SPToS3MovementPlan]:
#     """Create a DataMovementPlan from a list of movement plan dictionaries.

#     Args:
#         mode (Literal["write_to_s3", "write_to_sharepoint"] | None): The mode of
#             operation determining the type of movement plan to create.
#         data_movement_plan (list[config.S3ToSPMPDict] | list[config.SPToS3MPDict]):
#             A list of dictionaries representing the movement plans to be validated and
#             converted into a DataMovementPlan instance.

#     Returns:
#         list[config.S3ToSPMovementPlan] | list[config.SPToS3MovementPlan]:
#             A list of validated movement plans.

#     Raises:
#         ValueError: If an invalid mode is provided or if the movement plans are not
#             valid according to the specified mode.

#     Example movement plans:
#     -----------------------

#     For a Sharepoint file located at:
#     https://justiceuk.sharepoint.com/sites/analytics-site/Documents/reports/2026/daily_report.csv

#     ```
#     data_movement_plan=[
#         {
#             "source": {
#                 "site": "analytics-site",
#                 "library": "Documents",
#                 "directory": "reports/2026/",
#                 "filename": "daily_report.csv"
#             },
#             "destination": {
#                 "bucket": "my-destination-bucket",
#                 "key": "path/to/daily_report.csv"
#             }
#         }
#     ]
#     ```

#     for an S3 file located at:
#     s3://my-source-bucket/path/to/file1.csv

#     ```
#     data_movement_plan=[
#         {
#             "source": {
#                 "bucket": "my-source-bucket",
#                 "key": "path/to/file1.csv"
#             },
#             "destination": {
#                 "site": "analytics-site",
#                 "library": "Documents",
#                 "directory": "reports/2026/",
#                 "filename": "file1.csv"
#             }
#         }
#     ]
#     ```

#     """
#     load_dotenv()
#     mode = validate_mode(mode)

#     movement_plan_class = MODE_MAP[mode]["plan"]

#     movement_plan: list[config.S3ToSPMovementPlan] | list[config.SPToS3MovementPlan] = [  # type: ignore[assignment]
#         movement_plan_class(**movement_plan) for movement_plan in data_movement_plan
#     ]

#     return movement_plan
