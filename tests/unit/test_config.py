"""Unit tests for the config module."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from connector.config import (
    MovementPlan,
    S3Bucket,
    SecretConfig,
    SharePointLibrary,
)


def test_sharepointlibrary_valid_values() -> None:
    """Test that SharePointLibrary can be instantiated with valid fields."""
    lib = SharePointLibrary(site="analytics-site", library="Documents")
    assert lib.site == "analytics-site"
    assert lib.library == "Documents"


@pytest.mark.parametrize(
    ("invalid_site", "expected_error"),
    [
        ("", "site must be a non-empty string"),
        (
            "https://justiceuk.sharepoint.com/sites/analytics-site",
            "site should not include the 'https://justiceuk.sharepoint.com/sites/'",
        ),
    ],
)
def test_sharepointlibrary_invalid_sites(
    invalid_site: str, expected_error: str
) -> None:
    """Test that invalid site values raise ValidationError with expected message."""
    with pytest.raises(ValidationError, match=expected_error) as exc_info:
        SharePointLibrary(site=invalid_site, library="Documents")

    assert expected_error in str(exc_info.value)


def test_sharepointlibrary_empty_library() -> None:
    """Test that an empty library raises a validation error."""
    with pytest.raises(ValidationError, match="library must be a non-empty string"):
        SharePointLibrary(site="analytics-site", library="")


def test_s3bucket_valid_values() -> None:
    """Test that S3Bucket can be instantiated with a valid bucket name."""
    bucket = S3Bucket(bucket="my-bucket")
    assert bucket.bucket == "my-bucket"


@pytest.mark.parametrize(
    ("invalid_bucket", "expected_error"),
    [
        ("", "bucket must be a non-empty string"),
        ("s3://my-bucket", "should not include the 's3://' prefix"),
        ("my-bucket/", "should not end with a slash"),
    ],
)
def test_s3bucket_invalid_buckets(invalid_bucket: str, expected_error: str) -> None:
    """Test that invalid bucket values raise ValidationError with expected message."""
    with pytest.raises(ValidationError, match=expected_error) as exc_info:
        S3Bucket(bucket=invalid_bucket)

    assert expected_error in str(exc_info.value)


def test_secretconfig_load_from_env_vars() -> None:
    """Test that SecretConfig correctly loads environment variables."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    assert (
        UUID("12345678-9012-3456-7890-123456789012") == secrets.SECRET_AZURE_TENANT_ID
    )
    assert secrets.SECRET_AZURE_CLIENT_ID.get_secret_value() == "fake-client-id"
    assert secrets.SECRET_AZURE_CLIENT_SECRET.get_secret_value() == "fake-client-secret"


def test_movementplan_valid_values() -> None:
    """Test that MovementPlan stores source and destination strings."""
    plan = MovementPlan(
        source="reports/2026/file.csv",
        destination="path/to/file.csv",
    )
    assert plan.source == "reports/2026/file.csv"
    assert plan.destination == "path/to/file.csv"
