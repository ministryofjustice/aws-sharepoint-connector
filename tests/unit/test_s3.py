"""Unit tests for the s3 module."""

import boto3

from connector.config import ConnectorConfig
from connector.s3 import S3Connector
from tests import test_utils as utils


def test_download_from_s3_returns_file_content(s3: boto3.client) -> None:
    """Download returns the same bytes that were stored in S3."""
    config = ConnectorConfig()  # type: ignore[call-arg]
    expected = b"Column1,Column2\nValue1,10\nValue2,20\n"

    utils.create_bucket(config.S3_BUCKET, s3)
    s3.put_object(Bucket=config.S3_BUCKET, Key=config.FILE_KEY, Body=expected)

    connector = S3Connector(client=s3, bucket=config.S3_BUCKET, key=config.FILE_KEY)

    assert connector.download_from_s3() == expected


def test_upload_to_s3_writes_file_content(s3: boto3.client) -> None:
    """Upload writes bytes that can be read back from S3 unchanged."""
    config = ConnectorConfig()  # type: ignore[call-arg]
    data = b"name,score\nalice,100\nbob,95\n"

    utils.create_bucket(config.S3_BUCKET, s3)
    connector = S3Connector(client=s3, bucket=config.S3_BUCKET, key=config.FILE_KEY)

    connector.upload_to_s3(data)

    uploaded = s3.get_object(Bucket=config.S3_BUCKET, Key=config.FILE_KEY)[
        "Body"
    ].read()
    assert uploaded == data
