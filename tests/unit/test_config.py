"""Unit tests for the config module."""

import os
from uuid import UUID

from connector.config import SecretConfig


def test_config_loading() -> None:
    """Test that the SecretConfig class correctly loads environment variables."""
    os.environ["SP_FOLDER_PATH"] = "fake/folder/path"
    config = SecretConfig()  # type: ignore[call-arg]

    assert UUID("12345678-9012-3456-7890-123456789012") == config.SECRET_AZURE_TENANT_ID
    assert config.SECRET_AZURE_CLIENT_ID.get_secret_value() == "fake-client-id"
    assert config.SECRET_AZURE_CLIENT_SECRET.get_secret_value() == "fake-client-secret"
    assert config.SP_SITE_NAME == "fake-site-name"
    assert config.SP_LIBRARY_NAME == "Documents"
    assert config.SP_FOLDER_PATH == "fake/folder/path/"
    assert config.SP_FILE_NAME == "fake-file.csv"
    assert config.S3_BUCKET == "fake-bucket"
    assert config.FILE_KEY == "fake-file.csv"
    assert config.MODE == "write_to_s3"
