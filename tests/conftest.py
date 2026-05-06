"""Pytest fixtures for testing the AWS SharePoint Connector."""

from collections.abc import Generator

import boto3
import pytest
from moto import mock_aws


@pytest.fixture(name="s3")
def mock_s3() -> Generator[boto3.client]:
    """Return a mocked s3 client."""
    with mock_aws():
        yield boto3.client("s3", region_name="eu-west-2")


@pytest.fixture
def monkeypatch_session() -> Generator[pytest.MonkeyPatch]:
    """Create MonkeyPatch for setting environment variables."""
    m = pytest.MonkeyPatch()
    yield m
    m.undo()


@pytest.fixture(autouse=True)
def set_env_vars(monkeypatch_session: pytest.MonkeyPatch) -> None:
    """Run before all tests to create environment variables."""
    test_env_vars = {
        "SECRET_AZURE_TENANT_ID": "12345678901234567890123456789012",
        "SECRET_AZURE_CLIENT_ID": "fake-client-id",
        "SECRET_AZURE_CLIENT_SECRET": "fake-client-secret",  # pragma: allowlist secret
        "SP_SITE_NAME": "fake-site-name",
        "SP_LIBRARY_NAME": "Documents",
        "SP_FOLDER_PATH": "fake-folder-path",
        "SP_FILE_NAME": "fake-file.csv",
        "S3_BUCKET": "fake-bucket",
        "FILE_KEY": "directory/fake-file.csv",
        "MODE": "write_to_s3",
    }

    for key, value in test_env_vars.items():
        monkeypatch_session.setenv(key, value)
