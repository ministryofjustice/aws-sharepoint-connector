"""Unit tests for the main function of the connector application."""

import os
from unittest.mock import patch

import pytest

from connector import engine
from connector.exceptions import UploadError
from connector.main import main, setup_environment_variables
from tests.test_utils import sharepoint_connector_patches


def test_setup_environment_variables() -> None:
    """Test that the setup_environment_variables function sets environment variables."""
    env_vars = {
        "SP_FOLDER_PATH": "test/folder/path/",
        "SP_SITE_NAME": "test-site-name",
        "SP_LIBRARY_NAME": "TestDocuments",
        "SP_FILE_NAME": "test-file.csv",
        "S3_BUCKET": "test-bucket",
        "FILE_KEY": "test-file.csv",
        "MODE": "write_to_s3",
    }

    setup_environment_variables(env_vars)

    for var_name, var_value in env_vars.items():
        assert os.environ[var_name] == var_value


@pytest.mark.parametrize(
    ("mode", "exp_engine"),
    [
        ("write_to_s3", engine.UploadToS3Engine),
        ("write_to_sharepoint", engine.UploadToSharePointEngine),
    ],
)
def test_main_valid(mode: str, exp_engine: engine.Engine) -> None:
    """Test the main function of the connector application."""
    os.environ["MODE"] = mode

    with (
        sharepoint_connector_patches(),
        patch(
            "connector.engine.UploadToS3Engine.download_file",
            autospec=True,
            return_value=b"data",
        ) as s3_download,
        patch(
            "connector.engine.UploadToS3Engine.upload_file",
            autospec=True,
            return_value=None,
        ) as s3_upload,
        patch(
            "connector.engine.UploadToSharePointEngine.download_file",
            autospec=True,
            return_value=b"data",
        ) as sp_download,
        patch(
            "connector.engine.UploadToSharePointEngine.upload_file",
            autospec=True,
            return_value=None,
        ) as sp_upload,
    ):
        main()

    if mode == "write_to_s3":
        assert s3_download.call_count == 1
        assert s3_upload.call_count == 1
        assert sp_download.call_count == 0
        assert sp_upload.call_count == 0
        assert isinstance(s3_download.call_args[0][0], exp_engine)  # type: ignore[arg-type]
        assert isinstance(s3_upload.call_args[0][0], exp_engine)
    else:
        assert sp_download.call_count == 1
        assert sp_upload.call_count == 1
        assert s3_download.call_count == 0
        assert s3_upload.call_count == 0
        assert isinstance(sp_download.call_args[0][0], exp_engine)  # type: ignore[arg-type]
        assert isinstance(sp_upload.call_args[0][0], exp_engine)


def test_main_upload_error() -> None:
    """Test that the main function raises an error if the upload fails."""
    with (
        sharepoint_connector_patches(),
        patch(
            "connector.engine.UploadToS3Engine.download_file",
            autospec=True,
            side_effect=UploadError("Mock upload error"),
        ),
        pytest.raises(UploadError) as exc,
    ):
        main()

    assert "Mock upload error" in str(exc.value)


def test_main_provide_env_vars() -> None:
    """Test that the main function correctly sets environment variables passed to it."""
    env_vars = {
        "SP_FOLDER_PATH": "new/test/folder/",
        "SP_SITE_NAME": "new-test-site-name",
        "SP_LIBRARY_NAME": "NewDocuments",
        "SP_FILE_NAME": "new-test-file.csv",
        "S3_BUCKET": "new-test-bucket",
        "FILE_KEY": "new-test-file.csv",
        "MODE": "write_to_s3",
    }

    with (
        sharepoint_connector_patches(),
        patch(
            "connector.engine.UploadToS3Engine.download_file",
            autospec=True,
            return_value=b"data",
        ),
        patch(
            "connector.engine.UploadToS3Engine.upload_file",
            autospec=True,
            return_value=None,
        ),
        patch(
            "connector.main.setup_environment_variables",
        ) as mock_setup_env_vars,
    ):
        main(non_secret_env_vars=env_vars)

    assert mock_setup_env_vars.call_count == 1
    assert mock_setup_env_vars.call_args[0][0] == env_vars
