"""Unit tests for the engine module."""

from unittest.mock import patch

import boto3
import pytest

from connector import engine
from connector.config import MovementPlan, S3Bucket, SecretConfig
from connector.exceptions import UploadError
from tests import test_utils as utils

SP_FILE_PATH = utils.SP_FILE_PATH  # "reports/2026/file1.csv"
SP_FILE_NAME = utils.SP_FILE_NAME  # "file1.csv"
S3_KEY = utils.S3_KEY  # "path/to/file1.csv"
S3_BUCKET_NAME = utils.S3_BUCKET  # "my-source-bucket"
DEST_S3_BUCKET = "my-destination-bucket"


def test_upload_sharepoint_download_file_success(s3: boto3.client) -> None:
    """Test that download_file fetches the correct bytes from S3."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    library = utils.make_sharepoint_library()
    bucket = utils.make_s3_bucket()
    utils.create_bucket(S3_BUCKET_NAME, s3)
    df = utils.create_test_csv()
    expected = df.to_csv(index=False).encode("utf-8")
    s3.put_object(Bucket=S3_BUCKET_NAME, Key=S3_KEY, Body=expected)

    with utils.sharepoint_connector_patches():
        eng = engine.UploadToSharePointEngine(
            secrets=secrets, library=library, bucket=bucket
        )
        data = eng.download_file(S3_KEY)

    assert data == b"Column1,Column2,Column3\nValue1,10,A\nValue2,20,B\nValue3,30,C\n"


@pytest.mark.parametrize(
    "exception",
    [UploadError("s3 download failed")],
)
def test_upload_sharepoint_download_file_error(
    exception: Exception, s3: boto3.client
) -> None:
    """Test that download_file propagates UploadError from S3Connector."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    library = utils.make_sharepoint_library()
    bucket = utils.make_s3_bucket()
    utils.create_bucket(S3_BUCKET_NAME, s3)

    with (
        patch(
            "connector.engine.S3Connector.download_from_s3",
            side_effect=exception,
        ) as mock_download,
        utils.sharepoint_connector_patches(),
    ):
        eng = engine.UploadToSharePointEngine(
            secrets=secrets, library=library, bucket=bucket
        )
        with pytest.raises(UploadError):
            eng.download_file(S3_KEY)

    mock_download.assert_called_once_with()


def test_upload_sharepoint_upload_file_success() -> None:
    """Test that upload_file calls the correct SharePoint methods."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    library = utils.make_sharepoint_library()
    bucket = utils.make_s3_bucket()

    with (
        utils.sharepoint_connector_patches(
            extra_post_side_effects=[utils.mock_upload_url_response()],
            extra_get_side_effects=[
                utils.mock_verify_uploaded_file_response(200, SP_FILE_NAME, 12),
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
            secrets=secrets, library=library, bucket=bucket
        )
        eng.upload_file(b"Test content", SP_FILE_PATH)

    assert eng.sharepoint_connector.upload_url == "https://fake-upload-url"
    assert mock_session_put.call_count == 1
    assert mock_session_put.call_args[0][0] == "https://fake-upload-url"
    assert mock_session_put.call_args[1]["data"] == b"Test content"
    assert mock_session_get.call_count == 1
    assert mock_get.call_count == 3


def test_upload_s3_download_file_success() -> None:
    """Test that download_file returns the correct bytes from SharePoint."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    library = utils.make_sharepoint_library()
    bucket = S3Bucket(bucket=DEST_S3_BUCKET)

    with utils.sharepoint_connector_patches(
        extra_get_side_effects=[utils.mock_fetch_file_response(200)],
    ):
        eng = engine.UploadToS3Engine(secrets=secrets, library=library, bucket=bucket)
        data = eng.download_file(SP_FILE_PATH)

    assert (
        eng.sharepoint_connector.download_url
        == "https://graph.microsoft.com/v1.0/drives/fake-drive-id/root:/reports/2026/file1.csv:/content"
    )
    assert data == b'{"content": "fake-file-content"}'


@pytest.mark.parametrize(
    "exception",
    [
        UploadError("Mock upload error"),
        Exception("Mock error"),
    ],
)
def test_upload_s3_download_file_error(exception: Exception) -> None:
    """Test that download_file raises UploadError on SharePoint failures."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    library = utils.make_sharepoint_library()
    bucket = S3Bucket(bucket=DEST_S3_BUCKET)

    with (
        utils.sharepoint_connector_patches(),
        patch(
            "connector.engine.SharePointConnector.fetch_file",
            side_effect=exception,
        ),
    ):
        eng = engine.UploadToS3Engine(secrets=secrets, library=library, bucket=bucket)
        with pytest.raises(UploadError):
            eng.download_file(SP_FILE_PATH)

    assert (
        eng.sharepoint_connector.download_url
        == "https://graph.microsoft.com/v1.0/drives/fake-drive-id/root:/reports/2026/file1.csv:/content"
    )


def test_upload_s3_upload_file_success(s3: boto3.client) -> None:
    """Test that upload_file correctly writes content to S3."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    library = utils.make_sharepoint_library()
    bucket = S3Bucket(bucket=DEST_S3_BUCKET)
    utils.create_bucket(DEST_S3_BUCKET, s3)

    with utils.sharepoint_connector_patches():
        eng = engine.UploadToS3Engine(secrets=secrets, library=library, bucket=bucket)
        eng.upload_file(b"Test content", S3_KEY)

    file = s3.get_object(Bucket=DEST_S3_BUCKET, Key=S3_KEY)
    assert file["Body"].read() == b"Test content"


def test_engine_s3_client_created_once_on_init(s3: boto3.client) -> None:
    """Test that the S3 client is created once at engine init and reused."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    library = utils.make_sharepoint_library()
    bucket = utils.make_s3_bucket()

    with (
        utils.sharepoint_connector_patches(),
        patch("connector.engine.boto3.client", return_value=s3) as mock_boto3,
    ):
        eng = engine.UploadToSharePointEngine(
            secrets=secrets, library=library, bucket=bucket
        )

    assert mock_boto3.call_count == 1
    assert mock_boto3.call_args[0][0] == "s3"
    assert eng.s3_client is s3


def test_upload_sharepoint_validate_plans_success(s3: boto3.client) -> None:
    """validate_plans passes when S3 bucket/key and SharePoint folder all exist."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    library = utils.make_sharepoint_library()
    bucket = utils.make_s3_bucket()
    utils.create_bucket(S3_BUCKET_NAME, s3)
    s3.put_object(Bucket=S3_BUCKET_NAME, Key=S3_KEY, Body=b"data")

    plans = [MovementPlan(source=S3_KEY, destination=SP_FILE_PATH)]

    with utils.sharepoint_connector_patches(
        extra_get_side_effects=[utils.mock_check_folder_response(200, "2026")],
    ):
        eng = engine.UploadToSharePointEngine(
            secrets=secrets, library=library, bucket=bucket
        )
        eng.validate_plans(plans)  # should not raise


def test_upload_sharepoint_validate_plans_missing_source_key(s3: boto3.client) -> None:
    """validate_plans raises UploadError when the S3 source key is absent."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    library = utils.make_sharepoint_library()
    bucket = utils.make_s3_bucket()
    utils.create_bucket(S3_BUCKET_NAME, s3)  # bucket exists but key does not

    plans = [MovementPlan(source=S3_KEY, destination=SP_FILE_PATH)]

    with utils.sharepoint_connector_patches(
        extra_get_side_effects=[utils.mock_check_folder_response(200, "2026")],
    ):
        eng = engine.UploadToSharePointEngine(
            secrets=secrets, library=library, bucket=bucket
        )
        with pytest.raises(UploadError, match="Pre-flight validation failed"):
            eng.validate_plans(plans)


def test_upload_sharepoint_validate_plans_missing_destination_folder(
    s3: boto3.client,
) -> None:
    """validate_plans raises UploadError when no SharePoint destination folder."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    library = utils.make_sharepoint_library()
    bucket = utils.make_s3_bucket()
    utils.create_bucket(S3_BUCKET_NAME, s3)
    s3.put_object(Bucket=S3_BUCKET_NAME, Key=S3_KEY, Body=b"data")

    plans = [MovementPlan(source=S3_KEY, destination=SP_FILE_PATH)]

    with (
        utils.sharepoint_connector_patches(
            extra_get_side_effects=[utils.build_response(status_code=404)],
        ),
    ):
        eng = engine.UploadToSharePointEngine(
            secrets=secrets, library=library, bucket=bucket
        )
        with pytest.raises(UploadError, match="Pre-flight validation failed"):
            eng.validate_plans(plans)


def test_upload_sharepoint_validate_plans_collects_all_errors(s3: boto3.client) -> None:
    """validate_plans collects all errors and reports them together."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    library = utils.make_sharepoint_library()
    bucket = utils.make_s3_bucket()
    utils.create_bucket(S3_BUCKET_NAME, s3)  # bucket exists, but key is absent
    # folder also absent → 2 errors collected: missing key + missing folder

    plans = [MovementPlan(source=S3_KEY, destination=SP_FILE_PATH)]

    with (
        utils.sharepoint_connector_patches(
            extra_get_side_effects=[utils.build_response(status_code=404)],
        ),
    ):
        eng = engine.UploadToSharePointEngine(
            secrets=secrets, library=library, bucket=bucket
        )
        with pytest.raises(UploadError, match="2 error"):
            eng.validate_plans(plans)


def test_upload_sharepoint_validate_plans_bucket_not_found(s3: boto3.client) -> None:
    """validate_plans raises UploadError when the S3 source bucket does not exist."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    library = utils.make_sharepoint_library()
    bucket = utils.make_s3_bucket()

    plans = [MovementPlan(source=S3_KEY, destination="file.csv")]

    with utils.sharepoint_connector_patches():
        eng = engine.UploadToSharePointEngine(
            secrets=secrets, library=library, bucket=bucket
        )
        with pytest.raises(UploadError, match="Pre-flight validation failed"):
            eng.validate_plans(plans)


def test_upload_to_s3_validate_plans_success(s3: boto3.client) -> None:
    """validate_plans passes when S3 bucket is accessible and SharePoint file exists."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    library = utils.make_sharepoint_library()
    bucket = S3Bucket(bucket=DEST_S3_BUCKET)
    utils.create_bucket(DEST_S3_BUCKET, s3)

    plans = [MovementPlan(source=SP_FILE_PATH, destination=S3_KEY)]

    with utils.sharepoint_connector_patches(
        extra_get_side_effects=[utils.mock_check_file_response(200, SP_FILE_NAME)],
    ):
        eng = engine.UploadToS3Engine(secrets=secrets, library=library, bucket=bucket)
        eng.validate_plans(plans)  # should not raise


def test_upload_to_s3_validate_plans_missing_source_file(s3: boto3.client) -> None:
    """validate_plans raises UploadError when the SharePoint source file is absent."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    library = utils.make_sharepoint_library()
    bucket = S3Bucket(bucket=DEST_S3_BUCKET)
    utils.create_bucket(DEST_S3_BUCKET, s3)

    plans = [MovementPlan(source=SP_FILE_PATH, destination=S3_KEY)]

    with (
        utils.sharepoint_connector_patches(
            extra_get_side_effects=[utils.build_response(status_code=404)],
        ),
    ):
        eng = engine.UploadToS3Engine(secrets=secrets, library=library, bucket=bucket)
        with pytest.raises(UploadError, match="Pre-flight validation failed"):
            eng.validate_plans(plans)


def test_upload_to_s3_validate_plans_bucket_not_found(s3: boto3.client) -> None:
    """validate_plans raises UploadError when the S3 destination bucket is absent."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    library = utils.make_sharepoint_library()
    bucket = S3Bucket(bucket="non-existent-bucket")
    # bucket not created in moto

    plans = [MovementPlan(source=SP_FILE_PATH, destination=S3_KEY)]

    with (
        utils.sharepoint_connector_patches(
            extra_get_side_effects=[utils.mock_check_file_response(200, SP_FILE_NAME)],
        ),
    ):
        eng = engine.UploadToS3Engine(secrets=secrets, library=library, bucket=bucket)
        with pytest.raises(UploadError, match="Pre-flight validation failed"):
            eng.validate_plans(plans)
