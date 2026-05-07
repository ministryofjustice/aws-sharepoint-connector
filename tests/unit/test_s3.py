"""Unit tests for the s3 module."""

import boto3
import pytest

from connector.s3 import S3Connector
from tests import test_utils as utils


def test_download_from_s3_returns_file_content(s3: boto3.client) -> None:
    """Download returns the same bytes that were stored in S3."""
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]
    expected = b"Column1,Column2\nValue1,10\nValue2,20\n"

    utils.create_bucket(plan.data_to_move[0].s3_bucket, s3)
    s3.put_object(
        Bucket=plan.data_to_move[0].s3_bucket,
        Key=plan.data_to_move[0].s3_file_key,
        Body=expected,
    )

    connector = S3Connector(
        client=s3,
        bucket=plan.data_to_move[0].s3_bucket,
        key=plan.data_to_move[0].s3_file_key,
    )

    assert connector.download_from_s3() == expected


def test_upload_to_s3_writes_file_content(s3: boto3.client) -> None:
    """Upload writes bytes that can be read back from S3 unchanged."""
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]
    data = b"name,score\nalice,100\nbob,95\n"

    utils.create_bucket(plan.data_to_move[0].s3_bucket, s3)
    connector = S3Connector(
        client=s3,
        bucket=plan.data_to_move[0].s3_bucket,
        key=plan.data_to_move[0].s3_file_key,
    )

    connector.upload_to_s3(data)

    uploaded = s3.get_object(
        Bucket=plan.data_to_move[0].s3_bucket, Key=plan.data_to_move[0].s3_file_key
    )["Body"].read()
    assert uploaded == data


def test_verify_uploaded_object_success(s3: boto3.client) -> None:
    """verify_uploaded_object completes successfully when object size matches."""
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]
    data = b"test data"

    utils.create_bucket(plan.data_to_move[0].s3_bucket, s3)
    s3.put_object(
        Bucket=plan.data_to_move[0].s3_bucket,
        Key=plan.data_to_move[0].s3_file_key,
        Body=data,
    )

    connector = S3Connector(
        client=s3,
        bucket=plan.data_to_move[0].s3_bucket,
        key=plan.data_to_move[0].s3_file_key,
    )

    connector.verify_uploaded_object(expected_size=len(data))


def test_verify_uploaded_object_size_mismatch(s3: boto3.client) -> None:
    """verify_uploaded_object raises UploadError if object size doesn't match."""
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]
    data = b"test data"

    utils.create_bucket(plan.data_to_move[0].s3_bucket, s3)
    s3.put_object(
        Bucket=plan.data_to_move[0].s3_bucket,
        Key=plan.data_to_move[0].s3_file_key,
        Body=data,
    )

    connector = S3Connector(
        client=s3,
        bucket=plan.data_to_move[0].s3_bucket,
        key=plan.data_to_move[0].s3_file_key,
    )

    with pytest.raises(
        Exception,
        match="Verification failed for uploaded S3 object",
    ):
        connector.verify_uploaded_object(expected_size=len(data) + 1)


def test_verify_uploaded_object_not_found(s3: boto3.client) -> None:
    """verify_uploaded_object raises UploadError if object is not found in S3."""
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    utils.create_bucket(plan.data_to_move[0].s3_bucket, s3)

    connector = S3Connector(
        client=s3,
        bucket=plan.data_to_move[0].s3_bucket,
        key=plan.data_to_move[0].s3_file_key,
    )

    with pytest.raises(Exception, match="Failed to verify uploaded S3 object"):
        connector.verify_uploaded_object(expected_size=10)


def test_verify_uploaded_object_s3_error(s3: boto3.client) -> None:
    """verify_uploaded_object raises UploadError if S3 client raises an error."""
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    utils.create_bucket(plan.data_to_move[0].s3_bucket, s3)

    connector = S3Connector(
        client=s3,
        bucket=plan.data_to_move[0].s3_bucket,
        key=plan.data_to_move[0].s3_file_key,
    )

    with pytest.raises(Exception, match="Failed to verify uploaded S3 object"):
        connector.verify_uploaded_object(expected_size=10)
