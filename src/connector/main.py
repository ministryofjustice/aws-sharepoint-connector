"""Main entry point for the SharePoint connector application."""

import os
from typing import Literal, TypedDict

from connector import utils
from connector.config import (
    DataMovementPlan,
    S3ToSPMovementPlan,
    SecretConfig,
    SPToS3MovementPlan,
)
from connector.engine import UploadToS3Engine, UploadToSharePointEngine
from connector.exceptions import UploadError

log = utils.setup_logger()


class EngineMapDict(TypedDict):
    """TypedDict for mapping connector modes to movement plans and engines."""

    plan: type[S3ToSPMovementPlan | SPToS3MovementPlan]
    engine: type[UploadToSharePointEngine | UploadToS3Engine]


ENGINE_MAP: dict[str, EngineMapDict] = {
    "write_to_s3": {
        "plan": SPToS3MovementPlan,
        "engine": UploadToS3Engine,
    },
    "write_to_sharepoint": {
        "plan": S3ToSPMovementPlan,
        "engine": UploadToSharePointEngine,
    },
}


def run(
    mode: Literal["write_to_s3", "write_to_sharepoint"] | None = None,
    data_movement_plan: list[dict[str, dict[str, str]]] | None = None,
) -> None:
    """Entry point for the connector application.

    Args:
        mode (Literal["write_to_s3", "write_to_sharepoint"] | None): Optional
            argument to specify whether to copy a file from s3 to Sharepoint or
            vice versa. If not provided, the mode will be read from environment
            variables or a .env file.
        data_movement_plan (list[dict[str, dict[str, str]]] | None): Optional
            argument to specify the files to be moved and their destinations.
            If not provided, the movement plan will be read from environment variables
            or a .env file.

    Returns:
        None

    Example movement plans:
    -----------------------

    For a Sharepoint file located at:
    https://justiceuk.sharepoint.com/sites/analytics-site/Shared%20Documents/reports/2026/daily_report.csv

    ```
    data_movement_plan=[
        {
            "source": {
                "site": "analytics-site",
                "library": "Shared Documents",
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
                "library": "Shared Documents",
                "directory": "reports/2026/",
                "filename": "file1.csv"
            }
        }
    ]
    ```

    """
    log.info("Starting file transfer process...")

    run_mode = mode or os.getenv("MODE")

    if run_mode not in ENGINE_MAP:
        err = (
            f"Invalid mode '{run_mode}'. Must be one of: {', '.join(ENGINE_MAP.keys())}"
        )
        log.error(err)
        raise ValueError(err)

    if data_movement_plan is None:
        data_movement_plan_env = os.environ.get("DATA_MOVEMENT_PLAN")
        if not data_movement_plan_env:
            err = (
                "No data movement plan has been provided. Please provide movement plans"
                " via the 'DATA_MOVEMENT_PLAN' environment variable or as an argument"
                " to the run function."
            )
            log.error(err)
            raise ValueError(err)

        data_movement_plan = utils.parse_data_movement_plan_from_env(
            data_movement_plan_env
        )

    data_movement_plan = (
        [data_movement_plan]
        if isinstance(data_movement_plan, dict)
        else data_movement_plan
    )

    engine_class = ENGINE_MAP[run_mode]["engine"]
    movement_plan_class = ENGINE_MAP[run_mode]["plan"]
    secrets = SecretConfig()  # type: ignore[call-arg]

    all_movement_plans = [
        movement_plan_class(**movement_plan)
        for movement_plan in data_movement_plan  # type: ignore[arg-type]
    ]
    final_data_movement_plan = DataMovementPlan(**all_movement_plans)  # type: ignore[arg-type]

    for plan in final_data_movement_plan.data_to_move:
        engine = engine_class(config=secrets, plan=plan)

        try:
            content = engine.download_file()
            engine.upload_file(content)
            log.info("File transfer completed successfully.")
        except UploadError:
            log.exception("File transfer failed")
            raise


if __name__ == "__main__":
    run()  # pragma: no cover
