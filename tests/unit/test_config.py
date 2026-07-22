"""Unit tests for the config module."""

from uuid import UUID

import pytest
from pydantic import ValidationError

from aws_sharepoint_connector.config import (
    S3Bucket,
    SecretConfig,
    SharePointLibrary,
)


def test_sharepointlibrary_valid_values() -> None:
    """Test that SharePointLibrary can be instantiated with valid fields."""
    lib = SharePointLibrary(
        domain="organisation.sharepoint.com", site="analytics-site", library="Documents"
    )
    assert lib.domain == "organisation.sharepoint.com"
    assert lib.site == "analytics-site"
    assert lib.library == "Documents"


def test_sharepointlibrary_invalid_domain() -> None:
    """Test that invalid domain values raise ValidationError with expected message."""
    with pytest.raises(
        ValidationError, match="domain, site, and library must be non-empty strings"
    ):
        SharePointLibrary(domain="", site="analytics-site", library="Documents")


def test_sharepointlibrary_invalid_site() -> None:
    """Test that invalid site values raise ValidationError with expected message."""
    with pytest.raises(
        ValidationError, match="domain, site, and library must be non-empty strings"
    ):
        SharePointLibrary(
            domain="organisation.sharepoint.com", site="", library="Documents"
        )


def test_sharepointlibrary_empty_library() -> None:
    """Test that an empty library raises a validation error."""
    with pytest.raises(
        ValidationError, match="domain, site, and library must be non-empty strings"
    ):
        SharePointLibrary(
            domain="organisation.sharepoint.com", site="analytics-site", library=""
        )


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
