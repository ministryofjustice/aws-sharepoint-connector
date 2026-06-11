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


class TestSharePointLibrary:
    """Tests for SharePointLibrary validation."""

    def test_instantiation_with_valid_values(self) -> None:
        """Test that SharePointLibrary can be instantiated with valid fields."""
        lib = SharePointLibrary(site="analytics-site", library="Documents")
        assert lib.site == "analytics-site"
        assert lib.library == "Documents"

    def test_site_empty_raises(self) -> None:
        """Test that an empty site raises a validation error."""
        with pytest.raises(ValidationError, match="site must be a non-empty string"):
            SharePointLibrary(site="", library="Documents")

    def test_site_with_full_url_prefix_raises(self) -> None:
        """Test that a site with the full URL prefix raises a validation error."""
        with pytest.raises(ValidationError) as exc_info:
            SharePointLibrary(
                site="https://justiceuk.sharepoint.com/sites/analytics-site",
                library="Documents",
            )
        assert (
            "site should not include the 'https://justiceuk.sharepoint.com/sites/'"
            " prefix." in str(exc_info.value)
        )

    def test_library_empty_raises(self) -> None:
        """Test that an empty library raises a validation error."""
        with pytest.raises(ValidationError, match="library must be a non-empty string"):
            SharePointLibrary(site="analytics-site", library="")


class TestS3Bucket:
    """Tests for S3Bucket validation."""

    def test_instantiation_with_valid_value(self) -> None:
        """Test that S3Bucket can be instantiated with a valid bucket name."""
        bucket = S3Bucket(bucket="my-bucket")
        assert bucket.bucket == "my-bucket"

    def test_bucket_empty_raises(self) -> None:
        """Test that an empty bucket name raises a validation error."""
        with pytest.raises(ValidationError, match="bucket must be a non-empty string"):
            S3Bucket(bucket="")

    def test_bucket_with_s3_prefix_raises(self) -> None:
        """Test that a bucket with s3:// prefix raises a validation error."""
        with pytest.raises(
            ValidationError, match="should not include the 's3://' prefix"
        ):
            S3Bucket(bucket="s3://my-bucket")

    def test_bucket_with_trailing_slash_raises(self) -> None:
        """Test that a bucket with a trailing slash raises a validation error."""
        with pytest.raises(ValidationError, match="should not end with a slash"):
            S3Bucket(bucket="my-bucket/")


class TestMovementPlan:
    """Tests for MovementPlan."""

    def test_instantiation_stores_source_and_destination(self) -> None:
        """Test that MovementPlan stores source and destination strings."""
        plan = MovementPlan(
            source="reports/2026/file.csv",
            destination="path/to/file.csv",
        )
        assert plan.source == "reports/2026/file.csv"
        assert plan.destination == "path/to/file.csv"


class TestSecretConfig:
    """Tests for SecretConfig."""

    def test_loading_from_env_vars(self) -> None:
        """Test that SecretConfig correctly loads environment variables."""
        secrets = SecretConfig()  # type: ignore[call-arg]
        assert (
            UUID("12345678-9012-3456-7890-123456789012")
            == secrets.SECRET_AZURE_TENANT_ID
        )
        assert secrets.SECRET_AZURE_CLIENT_ID.get_secret_value() == "fake-client-id"
        assert (
            secrets.SECRET_AZURE_CLIENT_SECRET.get_secret_value()
            == "fake-client-secret"
        )

    def test_azure_tenant_id_is_uuid(self) -> None:
        """Test that SECRET_AZURE_TENANT_ID is stored as a UUID."""
        secrets = SecretConfig()  # type: ignore[call-arg]
        assert isinstance(secrets.SECRET_AZURE_TENANT_ID, UUID)

    def test_client_id_is_secret_str(self) -> None:
        """Test that SECRET_AZURE_CLIENT_ID is stored as SecretStr."""
        secrets = SecretConfig()  # type: ignore[call-arg]
        assert callable(secrets.SECRET_AZURE_CLIENT_ID.get_secret_value)

    def test_client_secret_is_secret_str(self) -> None:
        """Test that SECRET_AZURE_CLIENT_SECRET is stored as SecretStr."""
        secrets = SecretConfig()  # type: ignore[call-arg]
        assert callable(secrets.SECRET_AZURE_CLIENT_SECRET.get_secret_value)
