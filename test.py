"""Test file."""

import os

import boto3

from connector import create_engine
from connector.engine import UploadToS3Engine, UploadToSharePointEngine
from connector.exceptions import ProcessingError


def run_plans(
    plans: list[dict[str, str]],
    engine: UploadToSharePointEngine | UploadToS3Engine,
    *,
    delete: bool = False,
) -> None:
    """Run a list of file transfer plans using the given engine."""
    for plan in plans:
        engine.run(
            source=plan["source"], destination=plan["destination"], delete=delete
        )


def setup_test_environment() -> tuple[UploadToSharePointEngine, UploadToS3Engine]:
    """Set up test files in S3 and initialise engines."""
    s3 = boto3.client("s3")
    for i in range(1, 7):
        file_name = f"source/sample_s3_file_{i}.csv"
        s3.put_object(
            Bucket=os.environ["S3_BUCKET"],
            Key=file_name,
            Body=f"Sample data for file {i}",
        )

    to_sharepoint_engine: UploadToSharePointEngine = create_engine(  # type: ignore[assignment]
        mode="write_to_sharepoint",
        sp_site=os.environ["SP_SITE"],
        sp_library=os.environ["SP_LIBRARY"],
        s3_bucket=os.environ["S3_BUCKET"],
    )

    to_s3_engine: UploadToS3Engine = create_engine(  # type: ignore[assignment]
        mode="write_to_s3",
        sp_site=os.environ["SP_SITE"],
        sp_library=os.environ["SP_LIBRARY"],
        s3_bucket=os.environ["S3_BUCKET"],
    )

    return to_sharepoint_engine, to_s3_engine


def scenario_1(
    to_sharepoint_engine: UploadToSharePointEngine, to_s3_engine: UploadToS3Engine
) -> None:
    """Scenario 1: Write all files to SharePoint."""
    print("Starting Scenario 1: Writing all files to SharePoint")
    scenario_1_plan = [
        {
            "source": f"source/sample_s3_file_{i}.csv",
            "destination": f"scenario_1/sample_sp_file_{i}.csv",
        }
        for i in range(1, 7)
    ]

    run_plans(scenario_1_plan, to_sharepoint_engine)

    scenario_1_files = to_s3_engine.list_source_files()

    if all(
        file
        in [
            "scenario_1/sample_sp_file_1.csv",
            "scenario_1/sample_sp_file_2.csv",
            "scenario_1/sample_sp_file_3.csv",
            "scenario_1/sample_sp_file_4.csv",
            "scenario_1/sample_sp_file_5.csv",
            "scenario_1/sample_sp_file_6.csv",
        ]
        for file in scenario_1_files
    ):
        print("Test passed: All files are present in SharePoint.")
    else:
        print("Test failed: Some files are missing in SharePoint.")
        print("Found:", scenario_1_files)


def scenario_2(
    to_sharepoint_engine: UploadToSharePointEngine, to_s3_engine: UploadToS3Engine
) -> None:
    """Scenario 2: Write all files back to S3."""
    print("Starting Scenario 2: Writing all files back to S3")
    scenario_2_plan = [
        {
            "source": f"scenario_1/sample_sp_file_{i}.csv",
            "destination": f"scenario_2/sample_s3_file_{i}.csv",
        }
        for i in range(1, 7)
    ]

    run_plans(scenario_2_plan, to_s3_engine, delete=True)

    scenario_2_dest_files = to_sharepoint_engine.list_source_files()
    scenario_2_source_files = to_s3_engine.list_source_files()

    if all(
        file in scenario_2_dest_files
        for file in [
            "scenario_2/sample_s3_file_1.csv",
            "scenario_2/sample_s3_file_2.csv",
            "scenario_2/sample_s3_file_3.csv",
            "scenario_2/sample_s3_file_4.csv",
            "scenario_2/sample_s3_file_5.csv",
            "scenario_2/sample_s3_file_6.csv",
        ]
    ):
        print("Test passed: All files are present in S3.")
    else:
        print("Test failed: Some files are missing in S3.")
        print("Found:", scenario_2_dest_files)

    if any(
        file in scenario_2_source_files
        for file in [
            "scenario_1/sample_sp_file_1.csv",
            "scenario_1/sample_sp_file_2.csv",
            "scenario_1/sample_sp_file_3.csv",
            "scenario_1/sample_sp_file_4.csv",
            "scenario_1/sample_sp_file_5.csv",
            "scenario_1/sample_sp_file_6.csv",
        ]
    ):
        print("Test failed: Some files are still present in SharePoint.")
        print("Found:", scenario_2_source_files)
    else:
        print("Test passed: All files have been deleted from SharePoint.")


def scenario_3(
    to_sharepoint_engine: UploadToSharePointEngine, to_s3_engine: UploadToS3Engine
) -> None:
    """Scenario 3: Move some files to different locations & delete from S3."""
    print("Starting Scenario 3: Moving files to different locations & deleting from S3")
    scenario_3_plan = [
        {
            "source": "scenario_2/sample_s3_file_1.csv",
            "destination": "scenario_3/1/sample_sp_file_1.csv",
        },
        {
            "source": "scenario_2/sample_s3_file_2.csv",
            "destination": "scenario_3/2/sample_sp_file_2.csv",
        },
        {
            "source": "scenario_2/sample_s3_file_3.csv",
            "destination": "scenario_3/3/sample_sp_file_3.csv",
        },
    ]

    run_plans(scenario_3_plan, to_sharepoint_engine, delete=True)

    scenario_3_source_files = to_sharepoint_engine.list_source_files()
    scenario_3_destination_files = to_s3_engine.list_source_files()

    if all(
        file in scenario_3_destination_files
        for file in [
            "scenario_3/1/sample_sp_file_1.csv",
            "scenario_3/2/sample_sp_file_2.csv",
            "scenario_3/3/sample_sp_file_3.csv",
        ]
    ):
        print("Test passed: All files are present in SharePoint.")
    else:
        print("Test failed: Some files are missing in SharePoint.")
        print("Found:", scenario_3_destination_files)

    if any(
        file in scenario_3_source_files
        for file in [
            "scenario_2/sample_s3_file_1.csv",
            "scenario_2/sample_s3_file_2.csv",
            "scenario_2/sample_s3_file_3.csv",
        ]
    ):
        print("Test failed: Some files are still present in S3.")
        print("Found:", scenario_3_source_files)
    else:
        print("Test passed: All files have been deleted from S3.")


def scenario_4(
    to_sharepoint_engine: UploadToSharePointEngine, to_s3_engine: UploadToS3Engine
) -> None:
    """Scenario 4: Invalid plans."""
    print("Starting Scenario 4: Testing invalid plans")
    invalid_s3_key_plan = [
        {
            "source": "invalid/key.csv",
            "destination": "scenario_4/invalid_key.csv",
        },
    ]
    try:
        run_plans(invalid_s3_key_plan, to_sharepoint_engine)
        print("Test failed: Expected error for invalid S3 key was not raised.")
    except ProcessingError as exc:
        print(f"Test passed: Caught expected error for invalid S3 key: {exc}")

    invalid_sp_folder_plan = [
        {
            "source": "source/sample_s3_file_1.csv",
            "destination": "invalid_folder/sample_s4_file_1.csv",
        },
    ]
    try:
        run_plans(invalid_sp_folder_plan, to_sharepoint_engine)
        print(
            "Test failed: Expected error for invalid SharePoint folder was not raised."
        )
    except ProcessingError as exc:
        print(
            f"Test passed: Caught expected error for invalid SharePoint folder: {exc}"
        )

    invalid_sp_file_plan = [
        {
            "source": "scenario_3/1/invalid_file.csv",
            "destination": "scenario_4/invalid_file.csv",
        },
    ]
    try:
        run_plans(invalid_sp_file_plan, to_s3_engine)
        print("Test failed: Expected error for invalid SharePoint file was not raised.")
    except ProcessingError as exc:
        print(f"Test passed: Caught expected error for invalid SharePoint file: {exc}")

    invalid_bucket_engine = create_engine(
        mode="write_to_sharepoint",
        sp_site=os.environ["SP_SITE"],
        sp_library=os.environ["SP_LIBRARY"],
        s3_bucket="invalid_bucket",
    )

    invalid_s3_bucket_plan = [
        {
            "source": "invalid_bucket/sample_s3_file_1.csv",
            "destination": "scenario_4/sample_s3_file_1.csv",
        },
    ]

    try:
        run_plans(invalid_s3_bucket_plan, invalid_bucket_engine)
        print("Test failed: Expected error for invalid S3 bucket was not raised.")
    except ProcessingError as exc:
        print(f"Test passed: Caught expected error for invalid S3 bucket: {exc}")


def main() -> None:
    """Run the test scenarios for transferring files between S3 and SharePoint."""
    ### Set up files and engines
    to_sharepoint_engine, to_s3_engine = setup_test_environment()

    ### Scenario 1: Write all files to SharePoint
    scenario_1(to_sharepoint_engine, to_s3_engine)

    ### Scenario 2: Write all files back to S3
    scenario_2(to_sharepoint_engine, to_s3_engine)

    ### Scenario 3: Move some files to different locations & delete from S3
    scenario_3(to_sharepoint_engine, to_s3_engine)

    ### Scenario 4: Invalid plans
    scenario_4(to_sharepoint_engine, to_s3_engine)


if __name__ == "__main__":
    main()
