"""Test file."""

import os
from typing import Literal

import boto3

from aws_sharepoint_connector import create_engine
from aws_sharepoint_connector.engine import UploadToS3Engine, UploadToSharePointEngine
from aws_sharepoint_connector.exceptions import ProcessingError

# Scenarios

# 1) Write all files to SharePoint (retain source files)
# 2) Write all files back to S3 (retain source files)
# 3) Write some files to SharePoint (delete source files)
# 4) Write some files to S3 (delete source files)
# 5) Write files to different SharePoint folders (archive source files)
# 6) Write files to different S3 folders (archive source files)
# 7) Invalid plans (invalid S3 key, SharePoint folder, SharePoint file, S3 bucket)


def run_plans(
    plans: list[dict[str, str]],
    engine: UploadToSharePointEngine | UploadToS3Engine,
    archive_folder: str = "",
    *,
    source_handling: Literal["archive", "delete", "none"] = "none",
) -> None:
    """Run a list of file transfer plans using the given engine."""
    for plan in plans:
        engine.run(
            source=plan["source"],
            destination=plan["destination"],
            archive_folder=archive_folder,
            source_handling=source_handling,
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

    s3_to_sharepoint_engine: UploadToSharePointEngine = create_engine(  # type: ignore[assignment]
        mode="write_to_sharepoint",
        sp_site=os.environ["SP_SITE"],
        sp_library=os.environ["SP_LIBRARY"],
        s3_bucket=os.environ["S3_BUCKET"],
    )

    sp_to_s3_engine: UploadToS3Engine = create_engine(  # type: ignore[assignment]
        mode="write_to_s3",
        sp_site=os.environ["SP_SITE"],
        sp_library=os.environ["SP_LIBRARY"],
        s3_bucket=os.environ["S3_BUCKET"],
    )

    return s3_to_sharepoint_engine, sp_to_s3_engine


def scenario_1(
    s3_to_sharepoint_engine: UploadToSharePointEngine, sp_to_s3_engine: UploadToS3Engine
) -> None:
    """Scenario 1: Write all files to SharePoint (retain source files)."""
    print("Starting Scenario 1...")
    scenario_1_plan = [
        {
            "source": f"source/sample_s3_file_{i}.csv",
            "destination": f"scenario_1/sample_sp_file_{i}.csv",
        }
        for i in range(1, 7)
    ]

    run_plans(scenario_1_plan, s3_to_sharepoint_engine, source_handling="none")

    s1_source_files = s3_to_sharepoint_engine.list_source_files()
    s1_dest_files = sp_to_s3_engine.list_source_files()

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
        for file in s1_dest_files
    ):
        if all(
            file
            in [
                "source/sample_s3_file_1.csv",
                "source/sample_s3_file_2.csv",
                "source/sample_s3_file_3.csv",
                "source/sample_s3_file_4.csv",
                "source/sample_s3_file_5.csv",
                "source/sample_s3_file_6.csv",
            ]
            for file in s1_source_files
        ):
            print("Test passed: All files are present in SharePoint.")
        else:
            print("Test failed: Some files are missing in S3.")
            print("Found:", s1_source_files)
    else:
        print("Test failed: Some files are missing in SharePoint.")
        print("Found:", s1_dest_files)


def scenario_2(
    s3_to_sharepoint_engine: UploadToSharePointEngine, sp_to_s3_engine: UploadToS3Engine
) -> None:
    """Scenario 2: Write all files back to S3 (retain source files)."""
    print("Starting Scenario 2...")
    scenario_2_plan = [
        {
            "source": f"scenario_1/sample_sp_file_{i}.csv",
            "destination": f"scenario_2/sample_s3_file_{i}.csv",
        }
        for i in range(1, 7)
    ]

    run_plans(scenario_2_plan, sp_to_s3_engine, source_handling="none")

    s2_source_files = sp_to_s3_engine.list_source_files()
    s2_dest_files = s3_to_sharepoint_engine.list_source_files()

    if all(
        file in s2_dest_files
        for file in [
            "scenario_2/sample_s3_file_1.csv",
            "scenario_2/sample_s3_file_2.csv",
            "scenario_2/sample_s3_file_3.csv",
            "scenario_2/sample_s3_file_4.csv",
            "scenario_2/sample_s3_file_5.csv",
            "scenario_2/sample_s3_file_6.csv",
        ]
    ):
        if all(
            file in s2_source_files
            for file in [
                "scenario_1/sample_sp_file_1.csv",
                "scenario_1/sample_sp_file_2.csv",
                "scenario_1/sample_sp_file_3.csv",
                "scenario_1/sample_sp_file_4.csv",
                "scenario_1/sample_sp_file_5.csv",
                "scenario_1/sample_sp_file_6.csv",
            ]
        ):
            print("Test passed: All files are present in S3.")
        else:
            print("Test failed: Some files are missing in S3.")
            print("Found:", s2_dest_files)
    else:
        print("Test failed: Some files are missing in SharePoint.")
        print("Found:", s2_source_files)


def scenario_3(
    s3_to_sharepoint_engine: UploadToSharePointEngine, sp_to_s3_engine: UploadToS3Engine
) -> None:
    """Scenario 3: Write some files to SharePoint (delete source files)."""
    print("Starting Scenario 3...")
    scenario_3_plan = [
        {
            "source": f"scenario_2/sample_s3_file_{i}.csv",
            "destination": f"scenario_3/sample_sp_file_{i}.csv",
        }
        for i in range(1, 7)
    ]

    run_plans(scenario_3_plan, s3_to_sharepoint_engine, source_handling="delete")

    s3_source_files = s3_to_sharepoint_engine.list_source_files()
    s3_dest_files = sp_to_s3_engine.list_source_files()

    if all(
        file in s3_dest_files
        for file in [
            "scenario_3/sample_sp_file_1.csv",
            "scenario_3/sample_sp_file_2.csv",
            "scenario_3/sample_sp_file_3.csv",
            "scenario_3/sample_sp_file_4.csv",
            "scenario_3/sample_sp_file_5.csv",
            "scenario_3/sample_sp_file_6.csv",
        ]
    ):
        if any(
            file in s3_source_files
            for file in [
                "scenario_2/sample_s3_file_1.csv",
                "scenario_2/sample_s3_file_2.csv",
                "scenario_2/sample_s3_file_3.csv",
                "scenario_2/sample_s3_file_4.csv",
                "scenario_2/sample_s3_file_5.csv",
                "scenario_2/sample_s3_file_6.csv",
            ]
        ):
            print("Test failed: Some source files were not deleted from S3.")
        else:
            print("Test passed: All source files were copied and deleted correctly.")
    else:
        print("Test failed: Some files are missing in SharePoint.")
        print("Found:", s3_dest_files)


def scenario_4(
    s3_to_sharepoint_engine: UploadToSharePointEngine, sp_to_s3_engine: UploadToS3Engine
) -> None:
    """Scenario 4: Write some files to S3 (delete source files)."""
    print("Starting Scenario 4...")
    scenario_4_plan = [
        {
            "source": f"scenario_3/sample_sp_file_{i}.csv",
            "destination": f"scenario_4/sample_s3_file_{i}.csv",
        }
        for i in range(1, 7)
    ]

    run_plans(scenario_4_plan, sp_to_s3_engine, source_handling="delete")

    sp_source_files = sp_to_s3_engine.list_source_files()
    sp_dest_files = s3_to_sharepoint_engine.list_source_files()

    if all(
        file in sp_dest_files
        for file in [
            "scenario_4/sample_s3_file_1.csv",
            "scenario_4/sample_s3_file_2.csv",
            "scenario_4/sample_s3_file_3.csv",
            "scenario_4/sample_s3_file_4.csv",
            "scenario_4/sample_s3_file_5.csv",
            "scenario_4/sample_s3_file_6.csv",
        ]
    ):
        if any(
            file in sp_source_files
            for file in [
                "scenario_3/sample_sp_file_1.csv",
                "scenario_3/sample_sp_file_2.csv",
                "scenario_3/sample_sp_file_3.csv",
                "scenario_3/sample_sp_file_4.csv",
                "scenario_3/sample_sp_file_5.csv",
                "scenario_3/sample_sp_file_6.csv",
            ]
        ):
            print("Test failed: Some source files were not deleted from SharePoint.")
        else:
            print("Test passed: All source files were copied and deleted correctly.")
    else:
        print("Test failed: Some files are missing in S3.")
        print("Found:", sp_dest_files)


def scenario_5(
    s3_to_sharepoint_engine: UploadToSharePointEngine, sp_to_s3_engine: UploadToS3Engine
) -> None:
    """Scenario 5: Write files to different SharePoint folders (archive files)."""
    print("Starting Scenario 5...")
    scenario_5_plan = [
        {
            "source": f"scenario_4/sample_s3_file_{i}.csv",
            "destination": f"scenario_5/folder_{i}/sample_sp_file_{i}.csv",
        }
        for i in range(1, 4)
    ]

    run_plans(
        scenario_5_plan, s3_to_sharepoint_engine, "archive", source_handling="archive"
    )

    s5_source_files = s3_to_sharepoint_engine.list_source_files()
    s5_dest_files = sp_to_s3_engine.list_source_files()

    if all(
        file in s5_dest_files
        for file in [
            "scenario_5/folder_1/sample_sp_file_1.csv",
            "scenario_5/folder_2/sample_sp_file_2.csv",
            "scenario_5/folder_3/sample_sp_file_3.csv",
        ]
    ):
        if (
            all(
                file in s5_source_files
                for file in [
                    "archive/sample_s3_file_1.csv",
                    "archive/sample_s3_file_2.csv",
                    "archive/sample_s3_file_3.csv",
                ]
            )
            and all(
                file not in s5_source_files
                for file in [
                    "scenario_4/sample_s3_file_1.csv",
                    "scenario_4/sample_s3_file_2.csv",
                    "scenario_4/sample_s3_file_3.csv",
                ]
            )
            and all(
                file in s5_source_files
                for file in [
                    "scenario_4/sample_s3_file_4.csv",
                    "scenario_4/sample_s3_file_5.csv",
                    "scenario_4/sample_s3_file_6.csv",
                ]
            )
        ):
            print("Test passed: All files are present correctly in S3 and SharePoint.")
        else:
            print("Test failed: Some files were not archived correctly.")
            print("Found:", s5_source_files)
    else:
        print("Test failed: Some files are missing in SharePoint.")
        print("Found:", s5_dest_files)


def scenario_6(
    s3_to_sharepoint_engine: UploadToSharePointEngine, sp_to_s3_engine: UploadToS3Engine
) -> None:
    """Scenario 6: Write files to different S3 folders (archive files)."""
    print("Starting Scenario 6...")
    scenario_6_plan = [
        {
            "source": f"scenario_5/folder_{i}/sample_sp_file_{i}.csv",
            "destination": f"scenario_6/folder_{i}/sample_s3_file_{i}.csv",
        }
        for i in range(1, 3)
    ]

    run_plans(scenario_6_plan, sp_to_s3_engine, "archive", source_handling="archive")

    s6_source_files = sp_to_s3_engine.list_source_files()
    s6_dest_files = s3_to_sharepoint_engine.list_source_files()

    if all(
        file in s6_dest_files
        for file in [
            "scenario_6/folder_1/sample_s3_file_1.csv",
            "scenario_6/folder_2/sample_s3_file_2.csv",
        ]
    ):
        if (
            all(
                file in s6_source_files
                for file in [
                    "archive/sample_sp_file_1.csv",
                    "archive/sample_sp_file_2.csv",
                ]
            )
            and all(
                file not in s6_source_files
                for file in [
                    "scenario_5/folder_1/sample_sp_file_1.csv",
                    "scenario_5/folder_2/sample_sp_file_2.csv",
                ]
            )
            and all(
                file in s6_source_files
                for file in [
                    "scenario_5/folder_4/sample_sp_file_3.csv",
                ]
            )
        ):
            print("Test passed: All files are present correctly in S3 and SharePoint.")
        else:
            print("Test failed: Some files were not archived correctly.")
            print("Found:", s6_source_files)
    else:
        print("Test failed: Some files are missing in S3.")
        print("Found:", s6_dest_files)


def scenario_7(
    s3_to_sharepoint_engine: UploadToSharePointEngine, sp_to_s3_engine: UploadToS3Engine
) -> None:
    """Scenario 7: Invalid plans."""
    print("Starting Scenario 7: Testing invalid plans")
    invalid_s3_key_plan = [
        {
            "source": "invalid/key.csv",
            "destination": "scenario_4/invalid_key.csv",
        },
    ]
    try:
        run_plans(invalid_s3_key_plan, s3_to_sharepoint_engine)
        print("Test failed: Expected error for invalid S3 key was not raised.")
    except ProcessingError as exc:
        if "S3 object does not exist" in str(exc):
            print(f"Test passed: Caught expected error for invalid S3 key: {exc}")
        else:
            print(f"Test failed: Unexpected error for invalid S3 key: {exc}")

    invalid_sp_folder_plan = [
        {
            "source": "source/sample_s3_file_1.csv",
            "destination": "invalid_folder/sample_s4_file_1.csv",
        },
    ]
    try:
        run_plans(invalid_sp_folder_plan, s3_to_sharepoint_engine)
        print(
            "Test failed: Expected error for invalid SharePoint folder was not raised."
        )
    except ProcessingError as exc:
        if "not found in SharePoint" in str(exc):
            print(
                "Test passed: Caught expected error for invalid SharePoint folder:"
                f" {exc}"
            )
        else:
            print(f"Test failed: Unexpected error for invalid SharePoint folder: {exc}")

    invalid_sp_file_plan = [
        {
            "source": "scenario_3/1/invalid_file.csv",
            "destination": "scenario_4/invalid_file.csv",
        },
    ]
    try:
        run_plans(invalid_sp_file_plan, sp_to_s3_engine)
        print("Test failed: Expected error for invalid SharePoint file was not raised.")
    except ProcessingError as exc:
        if "not found in SharePoint" in str(exc):
            print(
                f"Test passed: Caught expected error for invalid SharePoint file: {exc}"
            )
        else:
            print(f"Test failed: Unexpected error for invalid SharePoint file: {exc}")

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
        if "S3 bucket does not exist" in str(exc):
            print(f"Test passed: Caught expected error for invalid S3 bucket: {exc}")
        else:
            print(f"Test failed: Unexpected error for invalid S3 bucket: {exc}")


def main() -> None:
    """Run the test scenarios for transferring files between S3 and SharePoint."""
    ### Set up files and engines
    s3_to_sharepoint_engine, sp_to_s3_engine = setup_test_environment()

    ### Scenario 1: Write all files to SharePoint
    scenario_1(s3_to_sharepoint_engine, sp_to_s3_engine)

    ### Scenario 2: Write all files back to S3
    scenario_2(s3_to_sharepoint_engine, sp_to_s3_engine)

    ### Scenario 3: Move some files to different locations & delete from S3
    scenario_3(s3_to_sharepoint_engine, sp_to_s3_engine)

    ### Scenario 4: Invalid plans
    scenario_4(s3_to_sharepoint_engine, sp_to_s3_engine)

    ### Scenario 5: Write files to different SharePoint folders (archive files)
    scenario_5(s3_to_sharepoint_engine, sp_to_s3_engine)

    ### Scenario 6: Write files to different S3 folders (archive files)
    scenario_6(s3_to_sharepoint_engine, sp_to_s3_engine)

    ### Scenario 7: Invalid plans
    scenario_7(s3_to_sharepoint_engine, sp_to_s3_engine)


if __name__ == "__main__":
    main()
