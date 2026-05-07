"""Unit tests for the engine module."""

from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import BotoCoreError, ClientError

from connector import engine
from connector.config import SecretConfig
from connector.exceptions import UploadError
from tests import test_utils as utils


def test_upload_sharepoint_download_file_success(s3: boto3.client) -> None:
    """Test that the method to download from s3 returns the correct data."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_s3_to_sp_movement_plan()
    utils.create_bucket(plan.data_to_move[0].s3_bucket, s3)
    df = utils.create_test_csv()

    s3.put_object(
        Bucket=plan.data_to_move[0].s3_bucket,
        Key=plan.data_to_move[0].s3_file_key,
        Body=df.to_csv(index=False).encode("utf-8"),
    )

    with utils.sharepoint_connector_patches():
        eng = engine.UploadToSharePointEngine(
            secrets=secrets, plan=plan.data_to_move[0]
        )
        data = eng.download_file()

    assert data == b"Column1,Column2,Column3\nValue1,10,A\nValue2,20,B\nValue3,30,C\n"


@pytest.mark.parametrize(
    "exception",
    [
        BotoCoreError(),
        ClientError(
            error_response={
                "Error": {"Code": "MockError", "Message": "Mock error message"}
            },
            operation_name="MockOperation",
        ),
    ],
)
def test_upload_sharepoint_download_file_error(
    exception: Exception, s3: boto3.client
) -> None:
    """Test that the method to download from s3 raises an UploadError."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_s3_to_sp_movement_plan()
    utils.create_bucket(plan.data_to_move[0].s3_bucket, s3)
    df = utils.create_test_csv()

    s3.put_object(
        Bucket=plan.data_to_move[0].s3_bucket,
        Key=plan.data_to_move[0].s3_file_key,
        Body=df.to_csv(index=False).encode("utf-8"),
    )

    with (
        patch(
            "connector.engine.S3Connector.download_from_s3",
            side_effect=exception,
        ) as mock_download,
        utils.sharepoint_connector_patches(),
    ):
        eng = engine.UploadToSharePointEngine(
            secrets=secrets, plan=plan.data_to_move[0]
        )
        with pytest.raises(UploadError):
            eng.download_file()

    mock_download.assert_called_once_with()


def test_upload_sharepoint_upload_file_success() -> None:
    """Test that the method to upload to SharePoint calls the correct methods."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_s3_to_sp_movement_plan()
    with (
        utils.sharepoint_connector_patches(
            extra_post_side_effects=[utils.mock_upload_url_response()],
            extra_get_side_effects=[
                utils.mock_verify_uploaded_file_response(
                    200, plan.data_to_move[0].sp_file_name, 12
                ),
            ],
        ) as (_, mock_get, _),
        patch(
            "connector.sharepoint.requests.Session.put",
            return_value=utils.mock_session_put_response(),
        ) as mock_session_put,
        patch(
            "connector.sharepoint.requests.Session.get",
            return_value=utils.mock_get_next_start_response(),
        ) as mock_session_get,
    ):
        eng = engine.UploadToSharePointEngine(
            secrets=secrets, plan=plan.data_to_move[0]
        )
        eng.upload_file(b"Test content")

    assert eng.sharepoint_connector.upload_url == "https://fake-upload-url"
    assert mock_session_put.call_count == 1
    assert mock_session_put.call_args[0][0] == "https://fake-upload-url"
    assert mock_session_put.call_args[1]["data"] == b"Test content"
    assert mock_session_get.call_count == 1
    assert mock_session_get.call_args[0][0] == "https://fake-upload-url"
    assert mock_get.call_count == 4


def test_upload_s3_download_file_success() -> None:
    """Test that the method to download from sharepoint returns the correct data."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_s3_to_sp_movement_plan()
    with utils.sharepoint_connector_patches(
        extra_get_side_effects=[utils.mock_fetch_file_response(200)],
    ):
        eng = engine.UploadToS3Engine(secrets=secrets, plan=plan.data_to_move[0])
        data = eng.download_file()

    assert (
        eng.sharepoint_connector.download_url
        == "https://graph.microsoft.com/v1.0/drives/fake-drive-id/root:/reports/2026/file1.csv:/content"
    )
    assert data == b'{"content": "fake-file-content"}'


def test_upload_s3_download_file_error() -> None:
    """Test that the method to download from sharepoint raises an error."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_s3_to_sp_movement_plan()
    with (
        utils.sharepoint_connector_patches(),
        patch(
            "connector.engine.SharePointConnector.fetch_file",
            side_effect=Exception("Mock error"),
        ),
    ):
        eng = engine.UploadToS3Engine(secrets=secrets, plan=plan.data_to_move[0])
        with pytest.raises(UploadError):
            eng.download_file()

    assert (
        eng.sharepoint_connector.download_url
        == "https://graph.microsoft.com/v1.0/drives/fake-drive-id/root:/reports/2026/file1.csv:/content"
    )


def test_upload_s3_upload_file_success(s3: boto3.client) -> None:
    """Test that the method to upload to s3 correctly uploads the file."""
    _, plan = utils.create_s3_to_sp_movement_plan()
    secrets = SecretConfig()  # type: ignore[call-arg]
    utils.create_bucket(plan.data_to_move[0].s3_bucket, s3)

    with utils.sharepoint_connector_patches():
        eng = engine.UploadToS3Engine(secrets=secrets, plan=plan.data_to_move[0])
        eng.upload_file(b"Test content")

    file = s3.get_object(
        Bucket=plan.data_to_move[0].s3_bucket, Key=plan.data_to_move[0].s3_file_key
    )
    content = file["Body"].read()
    assert content == b"Test content"
