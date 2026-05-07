"""Unit tests for the config module."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from connector.config import (
    DataMovementPlan,
    S3File,
    S3ToSPMovementPlan,
    SecretConfig,
    SharePointFile,
    SPToS3MovementPlan,
)


def test_sharepoint_file_instantiation_with_directory() -> None:
    """Test that SharePointFile can be instantiated with all fields."""
    sp_file = SharePointFile(
        site="analytics-site",
        library="Documents",
        directory="exports/reports/2026/04/",
        filename="daily_report.csv",
    )

    assert sp_file.site == "analytics-site"
    assert sp_file.library == "Documents"
    assert sp_file.directory == "exports/reports/2026/04/"
    assert sp_file.filename == "daily_report.csv"


def test_sharepoint_file_instantiation_without_directory() -> None:
    """Test that SharePointFile can be instantiated without directory."""
    sp_file = SharePointFile(
        site="analytics-site",
        library="Documents",
        filename="daily_report.csv",
    )

    assert sp_file.site == "analytics-site"
    assert sp_file.library == "Documents"
    assert sp_file.directory is None
    assert sp_file.filename == "daily_report.csv"


def test_sharepoint_file_validates_site_not_empty() -> None:
    """Test that SharePointFile validates site is not empty."""
    with pytest.raises(ValidationError) as exc_info:
        SharePointFile(
            site="",
            library="Documents",
            filename="file.csv",
        )
    assert "site must be a non-empty string" in str(exc_info.value)


def test_sharepoint_file_validates_site_no_prefix() -> None:
    """Test that SharePointFile validates site doesn't include URL prefix."""
    with pytest.raises(ValidationError) as exc_info:
        SharePointFile(
            site="https://justiceuk.sharepoint.com/sites/analytics-site",
            library="Documents",
            filename="file.csv",
        )
    assert (
        "site should not include the 'https://justiceuk.sharepoint.com/sites/' prefix."
        in str(exc_info.value)
    )


def test_s3_file_instantiation() -> None:
    """Test that S3File can be instantiated with valid data."""
    s3_file = S3File(bucket="my-bucket", key="path/to/file.csv")

    assert s3_file.bucket == "my-bucket"
    assert s3_file.key == "path/to/file.csv"


def test_s3_file_validates_bucket_not_empty() -> None:
    """Test that S3File validates bucket is not empty."""
    with pytest.raises(ValidationError) as exc_info:
        S3File(bucket="", key="path/to/file.csv")
    assert "bucket must be a non-empty string" in str(exc_info.value)


def test_s3_file_validates_bucket_no_s3_prefix() -> None:
    """Test that S3File validates bucket doesn't include s3:// prefix."""
    with pytest.raises(ValidationError) as exc_info:
        S3File(bucket="s3://my-bucket", key="path/to/file.csv")
    assert "should not include the 's3://' prefix" in str(exc_info.value)


def test_s3_file_validates_bucket_no_trailing_slash() -> None:
    """Test that S3File validates bucket doesn't end with slash."""
    with pytest.raises(ValidationError) as exc_info:
        S3File(bucket="my-bucket/", key="path/to/file.csv")
    assert "should not end with a slash" in str(exc_info.value)


def test_s3_file_validates_key_not_empty() -> None:
    """Test that S3File validates key is not empty."""
    with pytest.raises(ValidationError) as exc_info:
        S3File(bucket="my-bucket", key="")
    assert "key must be a non-empty string" in str(exc_info.value)


def test_s3_file_validates_key_not_folder() -> None:
    """Test that S3File validates key doesn't point to a folder."""
    with pytest.raises(ValidationError) as exc_info:
        S3File(bucket="my-bucket", key="path/to/folder/")
    assert "must point to a file not a folder" in str(exc_info.value)


def test_s3_file_validates_key_no_s3_prefix() -> None:
    """Test that S3File validates key doesn't include s3:// prefix."""
    with pytest.raises(ValidationError) as exc_info:
        S3File(bucket="my-bucket", key="s3://my-bucket/path/to/file.csv")
    error_msg = str(exc_info.value)
    assert "should not include the 's3://bucket-name/' prefix" in error_msg


def test_s3_file_validates_bucket_not_in_key() -> None:
    """Test that S3File validates bucket name is not included in key."""
    with pytest.raises(ValidationError) as exc_info:
        S3File(bucket="my-bucket", key="my-bucket/path/to/file.csv")
    assert "should not include the bucket name" in str(exc_info.value)


def test_s3_to_sp_movement_plan_instantiation() -> None:
    """Test that S3ToSPMovementPlan can be instantiated with valid data."""
    source = S3File(bucket="my-bucket", key="path/to/file.csv")
    destination = SharePointFile(
        site="analytics-site",
        library="Documents",
        directory="exports/",
        filename="file.csv",
    )

    plan = S3ToSPMovementPlan(source=source, destination=destination)

    assert plan.source == source
    assert plan.destination == destination


def test_s3_to_sp_movement_plan_properties() -> None:
    """Test that S3ToSPMovementPlan properties return expected values."""
    source = S3File(bucket="my-bucket", key="path/to/file.csv")
    destination = SharePointFile(
        site="analytics-site",
        library="Documents",
        directory="exports/",
        filename="file.csv",
    )

    plan = S3ToSPMovementPlan(source=source, destination=destination)

    assert plan.s3_bucket == "my-bucket"
    assert plan.s3_file_key == "path/to/file.csv"
    assert plan.sp_site == "analytics-site"
    assert plan.sp_library == "Documents"
    assert plan.sp_directory == "exports/"
    assert plan.sp_file_name == "file.csv"


def test_s3_to_sp_movement_plan_properties_no_directory() -> None:
    """Test that S3ToSPMovementPlan properties handle missing directory."""
    source = S3File(bucket="my-bucket", key="path/to/file.csv")
    destination = SharePointFile(
        site="analytics-site",
        library="Documents",
        filename="file.csv",
    )

    plan = S3ToSPMovementPlan(source=source, destination=destination)

    assert plan.sp_directory == ""


def test_sp_to_s3_movement_plan_instantiation() -> None:
    """Test that SPToS3MovementPlan can be instantiated with valid data."""
    source = SharePointFile(
        site="analytics-site",
        library="Documents",
        directory="exports/",
        filename="file.csv",
    )
    destination = S3File(bucket="my-bucket", key="path/to/file.csv")

    plan = SPToS3MovementPlan(source=source, destination=destination)

    assert plan.source == source
    assert plan.destination == destination


def test_sp_to_s3_movement_plan_properties() -> None:
    """Test that SPToS3MovementPlan properties return expected values."""
    source = SharePointFile(
        site="analytics-site",
        library="Documents",
        directory="exports/",
        filename="file.csv",
    )
    destination = S3File(bucket="my-bucket", key="path/to/file.csv")

    plan = SPToS3MovementPlan(source=source, destination=destination)

    assert plan.s3_bucket == "my-bucket"
    assert plan.s3_file_key == "path/to/file.csv"
    assert plan.sp_site == "analytics-site"
    assert plan.sp_library == "Documents"
    assert plan.sp_directory == "exports/"
    assert plan.sp_file_name == "file.csv"


def test_sp_to_s3_movement_plan_properties_no_directory() -> None:
    """Test that SPToS3MovementPlan properties handle missing directory."""
    source = SharePointFile(
        site="analytics-site",
        library="Documents",
        filename="file.csv",
    )
    destination = S3File(bucket="my-bucket", key="path/to/file.csv")

    plan = SPToS3MovementPlan(source=source, destination=destination)

    assert plan.sp_directory == ""


def test_data_movement_plan_single_s3_to_sp() -> None:
    """Test that DataMovementPlan can hold a single S3 to SP movement plan."""
    source = S3File(bucket="my-bucket", key="path/to/file.csv")
    destination = SharePointFile(
        site="analytics-site",
        library="Documents",
        filename="file.csv",
    )
    plan = S3ToSPMovementPlan(source=source, destination=destination)

    data_plan = DataMovementPlan(data_to_move=[plan])

    assert len(data_plan.data_to_move) == 1
    assert data_plan.data_to_move[0] == plan


def test_data_movement_plan_single_sp_to_s3() -> None:
    """Test that DataMovementPlan can hold a single SP to S3 movement plan."""
    source = SharePointFile(
        site="analytics-site",
        library="Documents",
        filename="file.csv",
    )
    destination = S3File(bucket="my-bucket", key="path/to/file.csv")
    plan = SPToS3MovementPlan(source=source, destination=destination)

    data_plan = DataMovementPlan(data_to_move=[plan])

    assert len(data_plan.data_to_move) == 1
    assert data_plan.data_to_move[0] == plan


def test_data_movement_plan_multiple_plans() -> None:
    """Test that DataMovementPlan can hold multiple movement plans."""
    plans_dict = [
        {
            "source": {
                "bucket": "my-source-bucket",
                "key": "path/to/file1.csv",
            },
            "destination": {
                "site": "analytics-site",
                "library": "Documents",
                "filename": "file1.csv",
            },
        },
        {
            "source": {
                "bucket": "my-source-bucket",
                "key": "path/to/file2.csv",
            },
            "destination": {
                "site": "analytics-site",
                "library": "Documents",
                "filename": "file2.csv",
            },
        },
    ]

    plans = [S3ToSPMovementPlan(**plan) for plan in plans_dict]  # type: ignore[arg-type]

    data_plan = DataMovementPlan(data_to_move=plans)  # type: ignore[arg-type]

    assert len(data_plan.data_to_move) == 2
    assert isinstance(data_plan.data_to_move[0], S3ToSPMovementPlan)
    assert isinstance(data_plan.data_to_move[1], S3ToSPMovementPlan)


def test_data_movement_plan_empty_list_invalid() -> None:
    """Test that DataMovementPlan requires at least one plan."""
    with pytest.raises(ValidationError):
        DataMovementPlan(data_to_move=[])


def test_secret_config_loading() -> None:
    """Test that SecretConfig correctly loads environment variables."""
    secrets = SecretConfig()  # type: ignore[call-arg]

    assert (
        UUID("12345678-9012-3456-7890-123456789012") == secrets.SECRET_AZURE_TENANT_ID
    )
    assert secrets.SECRET_AZURE_CLIENT_ID.get_secret_value() == "fake-client-id"
    assert secrets.SECRET_AZURE_CLIENT_SECRET.get_secret_value() == "fake-client-secret"


def test_secret_config_azure_tenant_id_is_uuid() -> None:
    """Test that SECRET_AZURE_TENANT_ID is stored as UUID."""
    secrets = SecretConfig()  # type: ignore[call-arg]

    assert isinstance(secrets.SECRET_AZURE_TENANT_ID, UUID)


def test_secret_config_client_id_is_secret() -> None:
    """Test that SECRET_AZURE_CLIENT_ID is stored as SecretStr."""
    secrets = SecretConfig()  # type: ignore[call-arg]

    # SecretStr provides get_secret_value() method
    assert callable(secrets.SECRET_AZURE_CLIENT_ID.get_secret_value)


def test_secret_config_client_secret_is_secret() -> None:
    """Test that SECRET_AZURE_CLIENT_SECRET is stored as SecretStr."""
    secrets = SecretConfig()  # type: ignore[call-arg]

    # SecretStr provides get_secret_value() method
    assert callable(secrets.SECRET_AZURE_CLIENT_SECRET.get_secret_value)
