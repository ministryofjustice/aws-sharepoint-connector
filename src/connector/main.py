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


def validate_mode(mode: str | None) -> str:
    """Validate that the provided mode is one of the allowed modes.

    Args:
        mode (str | None): The mode to validate.

    Returns:
        str: The validated mode.

    Raises:
        ValueError: If the mode is not valid.

    """
    run_mode = mode or os.getenv("MODE")
    if run_mode not in MODE_MAP:
        err = f"Invalid mode '{run_mode}'. Must be one of: {', '.join(MODE_MAP.keys())}"
        log.error(err)
        raise ValueError(err)
    return run_mode


def create_engine(
    mode: Literal["write_to_s3", "write_to_sharepoint"] | None = None,
) -> tuple[type[UploadToSharePointEngine | UploadToS3Engine], config.SecretConfig]:
    """Create an engine instance based on the mode.

    Args:
        mode (Literal["write_to_s3", "write_to_sharepoint"] | None): The mode of
            operation determining the type of engine to create.

    Returns:
        tuple[type[UploadToSharePointEngine | UploadToS3Engine], config.SecretConfig]:
            A tuple containing the engine class and the secrets configuration.

    Raises:
        ValueError: If an invalid mode is provided.

    """
    load_dotenv()
    run_mode = validate_mode(mode)

    secrets = config.SecretConfig()  # type: ignore[call-arg]

    log.info("Creating engine for mode: %s", run_mode)

    engine_class = MODE_MAP[run_mode]["engine"]
    return engine_class, secrets


def create_movement_plan(
    data_movement_plan: list[config.S3ToSPMPDict] | list[config.SPToS3MPDict],
    mode: Literal["write_to_s3", "write_to_sharepoint"] | None = None,
) -> config.DataMovementPlan:
    """Create a DataMovementPlan from a list of movement plan dictionaries.

    Args:
        mode (Literal["write_to_s3", "write_to_sharepoint"] | None): The mode of
            operation determining the type of movement plan to create.
        data_movement_plan (list[config.S3ToSPMPDict] | list[config.SPToS3MPDict]):
            A list of dictionaries representing the movement plans to be validated and
            converted into a DataMovementPlan instance.

    Returns:
        config.DataMovementPlan: An instance of DataMovementPlan containing the
            validated movement plans.

    Raises:
        ValueError: If an invalid mode is provided or if the movement plans are not
            valid according to the specified mode.

    Example movement plans:
    -----------------------

    For a Sharepoint file located at:
    https://justiceuk.sharepoint.com/sites/analytics-site/Documents/reports/2026/daily_report.csv

    ```
    data_movement_plan=[
        {
            "source": {
                "site": "analytics-site",
                "library": "Documents",
                "directory": "reports/2026/",
                "filename": "daily_report.csv"
            },
            "destination": {
                "bucket": "my-destination-bucket",
                "key": "path/to/daily_report.csv"
            }
        }
    ]
    ```

    for an S3 file located at:
    s3://my-source-bucket/path/to/file1.csv

    ```
    data_movement_plan=[
        {
            "source": {
                "bucket": "my-source-bucket",
                "key": "path/to/file1.csv"
            },
            "destination": {
                "site": "analytics-site",
                "library": "Documents",
                "directory": "reports/2026/",
                "filename": "file1.csv"
            }
        }
    ]
    ```

    """
    load_dotenv()
    run_mode = validate_mode(mode)

    movement_plan_class = MODE_MAP[run_mode]["plan"]

    all_movement_plans = [
        movement_plan_class(**movement_plan)  # type: ignore[arg-type]
        for movement_plan in data_movement_plan
    ]
    return config.DataMovementPlan(data_to_move=all_movement_plans)
