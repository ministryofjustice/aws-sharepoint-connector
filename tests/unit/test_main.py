"""Unit tests for the main function of the connector application."""

import os
from unittest.mock import patch

import pytest

from connector import engine
from connector.exceptions import UploadError
from connector.main import main
from tests.test_utils import sharepoint_connector_patches


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

    assert "File transfer failed: Mock upload error" in str(exc.value)
