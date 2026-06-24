"""Unit tests for the s3 module."""

from typing import Literal
from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import BotoCoreError, ClientError

from connector.exceptions import FileSizeMismatchError, ProcessingError
from connector.s3 import S3Connector
from tests import test_utils as utils

S3_BUCKET = utils.S3_BUCKET  # "my-source-bucket"
S3_KEY = utils.S3_KEY  # "path/to/file1.csv"


@pytest.fixture(autouse=True, name="connector")
def fixture_connector(s3: boto3.client) -> S3Connector:
    """Provide a S3Connector instance with the mocked s3 client."""
    return S3Connector(client=s3, bucket=S3_BUCKET)


def test_set_key(connector: S3Connector) -> None:
    """set_key sets the S3 key on the connector instance."""
    assert connector.source_key == ""  # default value
    connector.set_key(S3_KEY)
    assert connector.source_key == S3_KEY


def test_set_archive_key(connector: S3Connector) -> None:
    """set_archive_key sets the S3 archive key on the connector instance."""
    assert connector.archive_key == ""  # default value
    archive_key = "archive/path/to/file1.csv"
    connector.set_archive_key(archive_key)
    assert connector.archive_key == archive_key


@pytest.mark.parametrize(
    ("prefix", "expected_keys"),
    [
        ("include/", ["include/a.csv", "include/b.csv"]),
        ("", ["exclude/b.csv", "include/a.csv", "include/b.csv"]),
    ],
)
def test_list_objects_success(
    prefix: str, expected_keys: list[str], connector: S3Connector, s3: boto3.client
) -> None:
    """list_objects returns all keys in the bucket."""
    utils.create_bucket(S3_BUCKET, s3)
    utils.create_bucket("excluded-bucket", s3)
    s3.put_object(Bucket=S3_BUCKET, Key="include/a.csv", Body=b"data")
    s3.put_object(Bucket=S3_BUCKET, Key="include/b.csv", Body=b"data")
    s3.put_object(Bucket=S3_BUCKET, Key="exclude/b.csv", Body=b"data")
    s3.put_object(Bucket="excluded-bucket", Key="should/not/appear.csv", Body=b"data")
    assert sorted(connector.list_objects(prefix)) == expected_keys


def test_list_objects_empty_bucket(connector: S3Connector, s3: boto3.client) -> None:
    """list_objects returns an empty list for a bucket with no objects."""
    utils.create_bucket(S3_BUCKET, s3)
    connector = S3Connector(client=s3, bucket=S3_BUCKET)
    assert connector.list_objects() == []


def test_list_objects_pagination(connector: S3Connector, s3: boto3.client) -> None:
    """list_objects follows pagination to return all keys across multiple pages."""
    utils.create_bucket(S3_BUCKET, s3)
    page1 = {
        "Contents": [
            {"Key": "include/a.csv"},
            {"Key": "include/b.csv"},
        ],
        "IsTruncated": True,
        "NextContinuationToken": "token-xyz",
        "ResponseMetadata": {},
    }
    page2 = {
        "Contents": [{"Key": "include/d.csv"}],
        "IsTruncated": False,
        "ResponseMetadata": {},
    }
    with patch.object(s3, "list_objects_v2", side_effect=[page1, page2]):
        keys = connector.list_objects()
    assert keys == ["include/a.csv", "include/b.csv", "include/d.csv"]


@pytest.mark.parametrize(
    "exception",
    [
        BotoCoreError(),
        ClientError(
            {"Error": {"Code": "500", "Message": "Internal Error"}}, "ListObjectsV2"
        ),
    ],
)
def test_list_objects_error(
    exception: Exception, connector: S3Connector, s3: boto3.client
) -> None:
    """list_objects raises ProcessingError when the S3 request fails."""
    utils.create_bucket(S3_BUCKET, s3)
    with (
        patch.object(s3, "list_objects_v2", side_effect=exception),
        pytest.raises(
            ProcessingError, match="Failed to list objects in s3://"
        ) as exc_info,
    ):
        connector.list_objects()

    assert (
        str(exc_info.value)
        == f"Failed to list objects in s3://{S3_BUCKET}: {exception}"
    )


def test_download_from_s3_returns_file_content(
    connector: S3Connector, s3: boto3.client
) -> None:
    """Download returns the same bytes that were stored in S3."""
    expected = b"Column1,Column2\nValue1,10\nValue2,20\n"
    utils.create_bucket(S3_BUCKET, s3)
    s3.put_object(Bucket=S3_BUCKET, Key=S3_KEY, Body=expected)
    connector.set_key(S3_KEY)
    assert connector.download_from_s3() == expected


@pytest.mark.parametrize(
    "exception",
    [
        BotoCoreError(),
        ClientError({"Error": {"Message": "S3 client error"}}, "GetObject"),
    ],
)
def test_download_from_s3_error(
    connector: S3Connector, exception: Exception, s3: boto3.client
) -> None:
    """download_from_s3 raises ProcessingError with context when S3 client raises."""
    utils.create_bucket(S3_BUCKET, s3)
    connector.set_key(S3_KEY)

    with (
        patch.object(s3, "get_object", side_effect=exception),
        pytest.raises(ProcessingError, match="Failed to download s3://"),
    ):
        connector.download_from_s3()


def test_upload_to_s3_writes_file_content(
    connector: S3Connector, s3: boto3.client
) -> None:
    """Upload writes bytes that can be read back from S3 unchanged."""
    data = b"name,score\nalice,100\nbob,95\n"
    utils.create_bucket(S3_BUCKET, s3)

    connector.set_key(S3_KEY)
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
def test_upload_to_s3_error(
    connector: S3Connector, exception: Exception, s3: boto3.client
) -> None:
    """upload_to_s3 raises ProcessingError if S3 client raises an error."""
    utils.create_bucket(S3_BUCKET, s3)

    connector.set_key(S3_KEY)

    with (
        patch.object(s3, "put_object", side_effect=exception),
        pytest.raises(ProcessingError, match="Failed to upload object to s3://"),
    ):
        connector.upload_to_s3(b"data")


@pytest.mark.parametrize(("verify_type"), [("source"), ("archive")])
def test_verify_uploaded_object_success(
    verify_type: Literal["destination", "archive"],
    connector: S3Connector,
    s3: boto3.client,
) -> None:
    """verify_uploaded_object completes successfully when object size matches."""
    data = b"test data"
    utils.create_bucket(S3_BUCKET, s3)

    key = S3_KEY if verify_type == "destination" else "archive/path/to/file1.csv"

    s3.put_object(Bucket=S3_BUCKET, Key=key, Body=data)

    if verify_type == "destination":
        connector.set_key(key)
    else:
        connector.set_archive_key(key)

    connector.verify_uploaded_object(expected_size=len(data), verify_type=verify_type)


def test_verify_uploaded_object_size_mismatch(
    connector: S3Connector, s3: boto3.client
) -> None:
    """verify_uploaded_object raises FileSizeMismatchError if size does not match."""
    data = b"test data"
    utils.create_bucket(S3_BUCKET, s3)
    s3.put_object(Bucket=S3_BUCKET, Key=S3_KEY, Body=data)

    connector.set_key(S3_KEY)

    with pytest.raises(
        FileSizeMismatchError, match="Verification failed for uploaded S3 object"
    ):
        connector.verify_uploaded_object(
            expected_size=len(data) + 1, verify_type="destination"
        )


def test_verify_uploaded_object_not_found(
    connector: S3Connector, s3: boto3.client
) -> None:
    """verify_uploaded_object raises ProcessingError if the object does not exist."""
    utils.create_bucket(S3_BUCKET, s3)

    connector.set_key(S3_KEY)

    with pytest.raises(ProcessingError, match="Failed to verify uploaded S3 object"):
        connector.verify_uploaded_object(expected_size=10, verify_type="destination")


def test_verify_uploaded_object_archive_key_not_set(
    connector: S3Connector, s3: boto3.client
) -> None:
    """verify_uploaded_object raises ProcessingError if archive_key is not set."""
    utils.create_bucket(S3_BUCKET, s3)

    with pytest.raises(
        ProcessingError, match="archive_key must be set for archive verification"
    ):
        connector.verify_uploaded_object(expected_size=10, verify_type="archive")


def test_check_bucket_exists_success(connector: S3Connector, s3: boto3.client) -> None:
    """check_bucket_exists does not raise when the bucket is accessible."""
    utils.create_bucket(S3_BUCKET, s3)
    connector.check_bucket_exists()  # should not raise


def test_check_bucket_exists_not_found(
    connector: S3Connector, s3: boto3.client
) -> None:
    """check_bucket_exists raises ProcessingError when the bucket does not exist."""
    connector = S3Connector(client=s3, bucket="non-existent-bucket")
    with pytest.raises(ProcessingError, match="does not exist"):
        connector.check_bucket_exists()


def test_check_bucket_exists_access_denied(
    connector: S3Connector, s3: boto3.client
) -> None:
    """check_bucket_exists raises ProcessingError with an IAM hint on a 403 response."""
    utils.create_bucket(S3_BUCKET, s3)
    with (
        patch.object(
            s3,
            "head_bucket",
            side_effect=ClientError(
                {"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadBucket"
            ),
        ),
        pytest.raises(ProcessingError, match="Access denied"),
    ):
        connector.check_bucket_exists()


def test_check_bucket_exists_generic_client_error(
    connector: S3Connector, s3: boto3.client
) -> None:
    """check_bucket_exists raises ProcessingError with message for unknown codes."""
    utils.create_bucket(S3_BUCKET, s3)
    with (
        patch.object(
            s3,
            "head_bucket",
            side_effect=ClientError(
                {"Error": {"Code": "500", "Message": "Internal Server Error"}},
                "HeadBucket",
            ),
        ),
        pytest.raises(ProcessingError, match="Failed to access S3 bucket"),
    ):
        connector.check_bucket_exists()


def test_check_bucket_exists_botocore_error(
    connector: S3Connector, s3: boto3.client
) -> None:
    """check_bucket_exists raises ProcessingError when a BotoCoreError occurs."""
    utils.create_bucket(S3_BUCKET, s3)
    with (
        patch.object(s3, "head_bucket", side_effect=BotoCoreError()),
        pytest.raises(ProcessingError, match="Failed to access S3 bucket"),
    ):
        connector.check_bucket_exists()


def test_check_object_exists_success(connector: S3Connector, s3: boto3.client) -> None:
    """check_object_exists does not raise when the object is accessible."""
    utils.create_bucket(S3_BUCKET, s3)
    s3.put_object(Bucket=S3_BUCKET, Key=S3_KEY, Body=b"data")
    connector.set_key(S3_KEY)
    connector.check_object_exists()  # should not raise


def test_check_object_exists_not_found(
    connector: S3Connector, s3: boto3.client
) -> None:
    """check_object_exists raises ProcessingError when the object does not exist."""
    utils.create_bucket(S3_BUCKET, s3)
    connector.set_key("missing/key.csv")
    with pytest.raises(ProcessingError, match="does not exist"):
        connector.check_object_exists()


def test_check_object_exists_access_denied(
    connector: S3Connector, s3: boto3.client
) -> None:
    """check_object_exists raises ProcessingError with an IAM hint on a 403 response."""
    utils.create_bucket(S3_BUCKET, s3)
    connector.set_key(S3_KEY)
    with (
        patch.object(
            s3,
            "head_object",
            side_effect=ClientError(
                {"Error": {"Code": "403", "Message": "Forbidden"}}, "HeadObject"
            ),
        ),
        pytest.raises(ProcessingError, match="Access denied"),
    ):
        connector.check_object_exists()


def test_check_object_exists_generic_client_error(
    connector: S3Connector, s3: boto3.client
) -> None:
    """check_object_exists raises ProcessingError with message for unknown codes."""
    utils.create_bucket(S3_BUCKET, s3)
    connector.set_key(S3_KEY)
    with (
        patch.object(
            s3,
            "head_object",
            side_effect=ClientError(
                {"Error": {"Code": "500", "Message": "Internal Server Error"}},
                "HeadObject",
            ),
        ),
        pytest.raises(ProcessingError, match="Failed to access S3 object"),
    ):
        connector.check_object_exists()


def test_check_object_exists_botocore_error(
    connector: S3Connector, s3: boto3.client
) -> None:
    """check_object_exists raises ProcessingError when a BotoCoreError occurs."""
    utils.create_bucket(S3_BUCKET, s3)
    connector.set_key(S3_KEY)
    with (
        patch.object(s3, "head_object", side_effect=BotoCoreError()),
        pytest.raises(ProcessingError, match="Failed to access S3 object"),
    ):
        connector.check_object_exists()


def test_delete_object_success(connector: S3Connector, s3: boto3.client) -> None:
    """delete_object removes the current S3 key without raising."""
    utils.create_bucket(S3_BUCKET, s3)
    s3.put_object(Bucket=S3_BUCKET, Key=S3_KEY, Body=b"data")
    connector.set_key(S3_KEY)

    connector.delete_object()

    with pytest.raises(ProcessingError, match="does not exist"):
        connector.check_object_exists()


@pytest.mark.parametrize(
    "exception",
    [
        BotoCoreError(),
        ClientError({"Error": {"Message": "S3 client error"}}, "DeleteObject"),
    ],
)
def test_delete_object_error(
    connector: S3Connector, exception: Exception, s3: boto3.client
) -> None:
    """delete_object raises ProcessingError when the S3 client delete call fails."""
    utils.create_bucket(S3_BUCKET, s3)
    connector.set_key(S3_KEY)

    with (
        patch.object(s3, "delete_object", side_effect=exception),
        pytest.raises(ProcessingError, match="Failed to delete s3://"),
    ):
        connector.delete_object()
