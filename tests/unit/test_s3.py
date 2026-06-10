"""Unit tests for the s3 module."""

from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import BotoCoreError, ClientError

from connector.exceptions import UploadError
from connector.s3 import S3Connector
from tests import test_utils as utils

S3_BUCKET = utils.S3_BUCKET  # "my-source-bucket"
S3_KEY = utils.S3_KEY  # "path/to/file1.csv"


def test_download_from_s3_returns_file_content(s3: boto3.client) -> None:
    """Download returns the same bytes that were stored in S3."""
    expected = b"Column1,Column2\nValue1,10\nValue2,20\n"
    utils.create_bucket(S3_BUCKET, s3)
    s3.put_object(Bucket=S3_BUCKET, Key=S3_KEY, Body=expected)

    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    connector.update_with_key(S3_KEY)
    assert connector.download_from_s3() == expected


@pytest.mark.parametrize(
    "exception",
    [
        BotoCoreError(),
        ClientError({"Error": {"Message": "S3 client error"}}, "GetObject"),
    ],
)
def test_download_from_s3_error(s3: boto3.client, exception: Exception) -> None:
    """download_from_s3 raises UploadError with context when S3 client raises."""
    utils.create_bucket(S3_BUCKET, s3)

    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    connector.update_with_key(S3_KEY)

    with (
        patch.object(s3, "get_object", side_effect=exception),
        pytest.raises(UploadError, match="Failed to download s3://"),
    ):
        connector.download_from_s3()


def test_upload_to_s3_writes_file_content(s3: boto3.client) -> None:
    """Upload writes bytes that can be read back from S3 unchanged."""
    data = b"name,score\nalice,100\nbob,95\n"
    utils.create_bucket(S3_BUCKET, s3)

    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    connector.update_with_key(S3_KEY)
    connector.upload_to_s3(data)

    uploaded = s3.get_object(Bucket=S3_BUCKET, Key=S3_KEY)["Body"].read()
    assert uploaded == data


@pytest.mark.parametrize(
    "exception",
    [
        BotoCoreError(),
        ClientError({"Error": {"Message": "S3 client error"}}, "PutObject"),
    ],
)
def test_upload_to_s3_error(s3: boto3.client, exception: Exception) -> None:
    """upload_to_s3 raises UploadError if S3 client raises an error."""
    utils.create_bucket(S3_BUCKET, s3)

    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    connector.update_with_key(S3_KEY)

    with (
        patch.object(s3, "put_object", side_effect=exception),
        pytest.raises(UploadError, match="Failed to upload object to s3://"),
    ):
        connector.upload_to_s3(b"data")


def test_verify_uploaded_object_success(s3: boto3.client) -> None:
    """verify_uploaded_object completes successfully when object size matches."""
    data = b"test data"
    utils.create_bucket(S3_BUCKET, s3)
    s3.put_object(Bucket=S3_BUCKET, Key=S3_KEY, Body=data)

    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    connector.update_with_key(S3_KEY)
    connector.verify_uploaded_object(expected_size=len(data))


def test_verify_uploaded_object_size_mismatch(s3: boto3.client) -> None:
    """verify_uploaded_object raises UploadError if object size does not match."""
    data = b"test data"
    utils.create_bucket(S3_BUCKET, s3)
    s3.put_object(Bucket=S3_BUCKET, Key=S3_KEY, Body=data)

    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    connector.update_with_key(S3_KEY)

    with pytest.raises(UploadError, match="Verification failed for uploaded S3 object"):
        connector.verify_uploaded_object(expected_size=len(data) + 1)


def test_verify_uploaded_object_not_found(s3: boto3.client) -> None:
    """verify_uploaded_object raises UploadError if the object does not exist."""
    utils.create_bucket(S3_BUCKET, s3)

    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    connector.update_with_key(S3_KEY)

    with pytest.raises(UploadError, match="Failed to verify uploaded S3 object"):
        connector.verify_uploaded_object(expected_size=10)


def test_check_bucket_exists_success(s3: boto3.client) -> None:
    """check_bucket_exists does not raise when the bucket is accessible."""
    utils.create_bucket(S3_BUCKET, s3)
    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    connector.check_bucket_exists()  # should not raise


def test_check_bucket_exists_not_found(s3: boto3.client) -> None:
    """check_bucket_exists raises UploadError when the bucket does not exist."""
    connector = S3Connector(client=s3, bucket="non-existent-bucket")
    with pytest.raises(UploadError, match="does not exist"):
        connector.check_bucket_exists()


def test_check_bucket_exists_access_denied(s3: boto3.client) -> None:
    """check_bucket_exists raises UploadError with an IAM hint on a 403 response."""
    utils.create_bucket(S3_BUCKET, s3)
    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    with (
        patch.object(
            s3,
            "head_bucket",
            side_effect=ClientError(
                {"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadBucket"
            ),
        ),
        pytest.raises(UploadError, match="Access denied"),
    ):
        connector.check_bucket_exists()


def test_check_object_exists_success(s3: boto3.client) -> None:
    """check_object_exists does not raise when the object is accessible."""
    utils.create_bucket(S3_BUCKET, s3)
    s3.put_object(Bucket=S3_BUCKET, Key=S3_KEY, Body=b"data")
    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    connector.update_with_key(S3_KEY)
    connector.check_object_exists()  # should not raise


def test_check_object_exists_not_found(s3: boto3.client) -> None:
    """check_object_exists raises UploadError when the object does not exist."""
    utils.create_bucket(S3_BUCKET, s3)
    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    connector.update_with_key("missing/key.csv")
    with pytest.raises(UploadError, match="does not exist"):
        connector.check_object_exists()


def test_check_object_exists_access_denied(s3: boto3.client) -> None:
    """check_object_exists raises UploadError with an IAM hint on a 403 response."""
    utils.create_bucket(S3_BUCKET, s3)
    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    connector.update_with_key(S3_KEY)
    with (
        patch.object(
            s3,
            "head_object",
            side_effect=ClientError(
                {"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadObject"
            ),
        ),
        pytest.raises(UploadError, match="Access denied"),
    ):
        connector.check_object_exists()


def test_check_bucket_exists_generic_client_error(s3: boto3.client) -> None:
    """check_bucket_exists raises UploadError with generic message for unknown codes."""
    utils.create_bucket(S3_BUCKET, s3)
    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    with (
        patch.object(
            s3,
            "head_bucket",
            side_effect=ClientError(
                {"Error": {"Code": "500", "Message": "Internal Server Error"}},
                "HeadBucket",
            ),
        ),
        pytest.raises(UploadError, match="Failed to access S3 bucket"),
    ):
        connector.check_bucket_exists()


def test_check_bucket_exists_botocore_error(s3: boto3.client) -> None:
    """check_bucket_exists raises UploadError when a BotoCoreError occurs."""
    utils.create_bucket(S3_BUCKET, s3)
    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    with (
        patch.object(s3, "head_bucket", side_effect=BotoCoreError()),
        pytest.raises(UploadError, match="Failed to access S3 bucket"),
    ):
        connector.check_bucket_exists()


def test_check_object_exists_generic_client_error(s3: boto3.client) -> None:
    """check_object_exists raises UploadError with generic message for unknown codes."""
    utils.create_bucket(S3_BUCKET, s3)
    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    connector.update_with_key(S3_KEY)
    with (
        patch.object(
            s3,
            "head_object",
            side_effect=ClientError(
                {"Error": {"Code": "500", "Message": "Internal Server Error"}},
                "HeadObject",
            ),
        ),
        pytest.raises(UploadError, match="Failed to access S3 object"),
    ):
        connector.check_object_exists()


def test_check_object_exists_botocore_error(s3: boto3.client) -> None:
    """check_object_exists raises UploadError when a BotoCoreError occurs."""
    utils.create_bucket(S3_BUCKET, s3)
    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    connector.update_with_key(S3_KEY)
    with (
        patch.object(s3, "head_object", side_effect=BotoCoreError()),
        pytest.raises(UploadError, match="Failed to access S3 object"),
    ):
        connector.check_object_exists()


def test_list_objects_success(s3: boto3.client) -> None:
    """list_objects returns all keys in the bucket."""
    utils.create_bucket(S3_BUCKET, s3)
    s3.put_object(Bucket=S3_BUCKET, Key="a.csv", Body=b"data")
    s3.put_object(Bucket=S3_BUCKET, Key="b.csv", Body=b"data")
    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    assert sorted(connector.list_objects()) == ["a.csv", "b.csv"]


def test_list_objects_empty_bucket(s3: boto3.client) -> None:
    """list_objects returns an empty list for a bucket with no objects."""
    utils.create_bucket(S3_BUCKET, s3)
    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    assert connector.list_objects() == []


def test_list_objects_prefix(s3: boto3.client) -> None:
    """list_objects filters keys by the given prefix."""
    utils.create_bucket(S3_BUCKET, s3)
    s3.put_object(Bucket=S3_BUCKET, Key="reports/2026/a.csv", Body=b"data")
    s3.put_object(Bucket=S3_BUCKET, Key="reports/2026/b.csv", Body=b"data")
    s3.put_object(Bucket=S3_BUCKET, Key="other/c.csv", Body=b"data")
    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    result = connector.list_objects(prefix="reports/2026/")
    assert sorted(result) == ["reports/2026/a.csv", "reports/2026/b.csv"]


def test_list_objects_pagination(s3: boto3.client) -> None:
    """list_objects follows pagination to return all keys across multiple pages."""
    utils.create_bucket(S3_BUCKET, s3)
    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    page1 = {
        "Contents": [{"Key": "a.csv"}, {"Key": "b.csv"}],
        "IsTruncated": True,
        "NextContinuationToken": "token-xyz",
        "ResponseMetadata": {},
    }
    page2 = {
        "Contents": [{"Key": "c.csv"}],
        "IsTruncated": False,
        "ResponseMetadata": {},
    }
    with patch.object(s3, "list_objects_v2", side_effect=[page1, page2]):
        keys = connector.list_objects()
    assert keys == ["a.csv", "b.csv", "c.csv"]


def test_list_objects_error(s3: boto3.client) -> None:
    """list_objects raises UploadError when the S3 request fails."""
    utils.create_bucket(S3_BUCKET, s3)
    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    with (
        patch.object(
            s3,
            "list_objects_v2",
            side_effect=ClientError(
                {"Error": {"Code": "500", "Message": "Internal Error"}}, "ListObjectsV2"
            ),
        ),
        pytest.raises(UploadError, match="Failed to list objects in s3://"),
    ):
        connector.list_objects()


def test_delete_object_success(s3: boto3.client) -> None:
    """delete_object removes the current S3 key without raising."""
    utils.create_bucket(S3_BUCKET, s3)
    s3.put_object(Bucket=S3_BUCKET, Key=S3_KEY, Body=b"data")
    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    connector.update_with_key(S3_KEY)

    connector.delete_object()

    with pytest.raises(UploadError, match="does not exist"):
        connector.check_object_exists()


@pytest.mark.parametrize(
    "exception",
    [
        BotoCoreError(),
        ClientError({"Error": {"Message": "S3 client error"}}, "DeleteObject"),
    ],
)
def test_delete_object_error(s3: boto3.client, exception: Exception) -> None:
    """delete_object raises UploadError when the S3 client delete call fails."""
    utils.create_bucket(S3_BUCKET, s3)
    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    connector.update_with_key(S3_KEY)

    with (
        patch.object(s3, "delete_object", side_effect=exception),
        pytest.raises(UploadError, match="Failed to delete s3://"),
    ):
        connector.delete_object()
