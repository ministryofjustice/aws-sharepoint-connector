"""Main entry point for the SharePoint connector application."""

import os
from typing import Literal, TypedDict

from connector import utils
from connector.config import (
    SecretConfig,
    S3ToSPMovementPlan,
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
    movement_plans: list[dict[str, str | list[dict[str, str]]]] | None = None,
) -> None:
    """Entry point for the connector application.

    Args:
        mode (Literal["write_to_s3", "write_to_sharepoint"] | None): Optional
        argument to specify whether to copy a file from s3 to Sharepoint or
        vice versa. If not provided, the mode will be read from environment
        variables or a .env file.

        movement_plans (list[dict[str, str | list[dict[str, str]]]] | None): Optional
        argument to specify the files to be moved and their destinations.
        If not provided, the movement plan will be read from environment variables
        or a .env file.

    Returns:
        None

    Example movvement plans:
    -----------------------

    For a Sharepoint file located at:
    https://justiceuk.sharepoint.com/sites/analytics-site/Shared%20Documents/reports/2026/daily_report.csv

    ```
    movement_plan=[
        {
            "sp_site": "analytics-site",
            "files": [
                {
                    "source_sp_path": "Shared Documents/reports/2026/daily_report.csv",
                    "destination_s3_path": "bucket-name/path/in/s3/daily_report.csv",
                }
            ],
        }
    ]
    ```

    for an S3 file located at:
    s3://my-source-bucket/path/to/file1.csv

    ```
    movement_plan=[
        {
            "bucket": "my-source-bucket",
            "files": [
                {
                    "source_s3_key": "path/to/file1.csv",
                    "destination_sp_path": "Shared Documents/Folder1/file1.csv",
                }
            ],
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

    if movement_plans is None:
        movement_plans_env = os.environ.get("MOVEMENT_PLANS")
        if not movement_plans_env:
            err = (
                "No movement plans provided. Please provide movement plans via the"
                " 'MOVEMENT_PLANS' environment variable or as an argument to the run"
                " function."
            )
            log.error(err)
            raise ValueError(err)

        movement_plans = utils.parse_movement_plans_from_env(movement_plans_env)

    movement_plans = (
        [movement_plans] if isinstance(movement_plans, dict) else movement_plans
    )

    engine_class = ENGINE_MAP[run_mode]["engine"]
    movement_plan_class = ENGINE_MAP[run_mode]["plan"]
    secrets = SecretConfig()  # type: ignore[call-arg]

    for movement_plan in movement_plans:
        file_movement_plan = movement_plan_class(**movement_plan)  # type: ignore[arg-type]

        engine = engine_class(config=secrets, movement_plan=file_movement_plan)

        try:
            content = engine.download_file()
            engine.upload_file(content)
            log.info("File transfer completed successfully.")
        except UploadError:
            log.exception("File transfer failed")
            raise


if __name__ == "__main__":
    run()  # pragma: no cover
