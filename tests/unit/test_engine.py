"""Unit tests for the engine module."""

from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import BotoCoreError, ClientError

from connector import engine
from connector.exceptions import UploadError
from tests import test_utils as utils


def test_upload_sharepoint_download_file_success(s3: boto3.client) -> None:
    """Test that the SharePoint download method returns the correct data."""
    config = utils.create_test_config()
    utils.create_bucket(config.S3_BUCKET, s3)
    df = utils.create_test_csv()

    s3.put_object(
        Bucket=config.S3_BUCKET,
        Key=config.FILE_KEY,
        Body=df.to_csv(index=False).encode("utf-8"),
    )

    with utils.sharepoint_connector_init_patches():
        eng = engine.UploadToSharePointEngine(config)
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
    """Test that the SharePoint download method raises an UploadError on S3 errors."""
    config = utils.create_test_config()
    utils.create_bucket(config.S3_BUCKET, s3)
    df = utils.create_test_csv()

    s3.put_object(
        Bucket=config.S3_BUCKET,
        Key=config.FILE_KEY,
        Body=df.to_csv(index=False).encode("utf-8"),
    )

    with (
        patch(
            "connector.engine.S3Connector.download_from_s3",
            side_effect=exception,
        ) as mock_download,
        utils.sharepoint_connector_init_patches(),
    ):
        eng = engine.UploadToSharePointEngine(config)
        with pytest.raises(UploadError):
            eng.download_file()

    mock_download.assert_called_once_with()
