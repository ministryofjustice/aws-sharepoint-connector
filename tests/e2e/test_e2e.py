"""E2E tests for create_engine() + engine.copy(): write to S3 and SharePoint."""

from math import ceil
from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import ClientError
from requests import Response

from aws_sharepoint_connector.exceptions import InvalidPathError, ProcessingError
from aws_sharepoint_connector.main import create_engine
from tests import test_utils as utils


def create_test_data(size_mb: int) -> bytes:
    """Return deterministic test data of a specific size in megabytes."""
    return bytes([i % 256 for i in range(size_mb * 1024 * 1024)])


def build_binary_response(content: bytes) -> Response:
    """Return a binary response simulating a SharePoint file download."""
    response = Response()
    response.status_code = 200
    response._content = content
    response.headers["Content-Type"] = "application/octet-stream"
    return response


@pytest.mark.parametrize("file_count", [1, 6])
def test_e2e_write_to_s3(file_count: int, s3: boto3.client) -> None:
    """E2E test: download from SharePoint and upload to S3 for 1 and 6 files."""
    sp_site = utils.SP_SITE
    sp_library = utils.SP_LIBRARY
    s3_bucket = "my-destination-bucket"

    plans_dicts: list[dict[str, str]] = [
        {
            "source": f"reports/2026/file{i}.csv",
            "destination": f"path/to/file{i}.csv",
        }
        for i in range(1, file_count + 1)
    ]

    file_sizes_mb = [1] * file_count
    expected_payloads = [create_test_data(size) for size in file_sizes_mb]

    utils.create_bucket(s3_bucket, s3)

    get_mocks = [
        utils.mock_site_id_response(),
        utils.mock_drive_id_response("complete"),
    ]
    for i in range(1, file_count + 1):
        get_mocks.extend(
            [
                utils.mock_check_object_response(
                    200,
                    f"file{i}.csv",
                    "file",
                ),
                build_binary_response(expected_payloads[i - 1]),
            ]
        )

    with (
        patch(
            "aws_sharepoint_connector.auth.ClientSecretCredential.get_token",
            side_effect=utils.mock_get_token,
        ),
        patch(
            "aws_sharepoint_connector.sharepoint.requests.get", side_effect=get_mocks
        ),
    ):
        eng = create_engine("write_to_s3", sp_site, sp_library, s3_bucket)
        for plan in plans_dicts:
            eng.copy(plan["source"], plan["destination"])

    for _, (plan, expected_payload) in enumerate(
        zip(plans_dicts, expected_payloads, strict=True)
    ):
        obj = s3.get_object(Bucket=s3_bucket, Key=plan["destination"])
        assert obj["Body"].read() == expected_payload, (
            f"Data mismatch for {plan['destination']}"
        )


@pytest.mark.parametrize("file_count", [1, 6])
def test_e2e_write_to_sharepoint(file_count: int, s3: boto3.client) -> None:
    """E2E test: download from S3 and upload to SharePoint for 1 and 6 files."""
    sp_site = utils.SP_SITE
    sp_library = utils.SP_LIBRARY
    s3_bucket = utils.S3_BUCKET

    plans_dicts: list[dict[str, str]] = [
        {
            "source": f"path/to/file{i}.csv",
            "destination": f"reports/2026/file{i}.csv",
        }
        for i in range(1, file_count + 1)
    ]

    file_sizes_mb = [1] * file_count
    expected_payloads = [create_test_data(size) for size in file_sizes_mb]

    utils.create_bucket(s3_bucket, s3)

    for plan, payload in zip(plans_dicts, expected_payloads, strict=True):
        s3.put_object(Bucket=s3_bucket, Key=plan["source"], Body=payload)

    chunk_size = 10 * 1024 * 1024
    chunk_counts = [ceil((size * 1024 * 1024) / chunk_size) for size in file_sizes_mb]

    get_mocks: list[Response] = [
        utils.mock_site_id_response(),
        utils.mock_drive_id_response("complete"),
    ]
    for i in range(file_count):
        get_mocks.extend(
            [
                utils.mock_check_object_response(
                    200,
                    "reports/2026",
                    "folder",
                ),
                utils.mock_verify_uploaded_file_response(
                    200,
                    f"file{i + 1}.csv",
                    file_sizes_mb[i] * 1024 * 1024,
                ),
            ]
        )
    post_mocks = [utils.mock_upload_url_response() for _ in range(file_count)]
    session_get_mocks = [
        utils.mock_get_next_start_response() for _ in range(file_count)
    ]
    total_chunks = sum(chunk_counts)
    session_put_mocks = [utils.mock_session_put_response() for _ in range(total_chunks)]

    with (
        patch(
            "aws_sharepoint_connector.auth.ClientSecretCredential.get_token",
            side_effect=utils.mock_get_token,
        ),
        patch(
            "aws_sharepoint_connector.sharepoint.requests.get", side_effect=get_mocks
        ) as mock_sharepoint_gets,
        patch(
            "aws_sharepoint_connector.sharepoint.requests.post", side_effect=post_mocks
        ),
        patch(
            "aws_sharepoint_connector.sharepoint.requests.Session.get",
            side_effect=session_get_mocks,
        ),
        patch(
            "aws_sharepoint_connector.sharepoint.requests.Session.put",
            side_effect=session_put_mocks,
        ) as mock_session_put,
    ):
        eng = create_engine("write_to_sharepoint", sp_site, sp_library, s3_bucket)
        for plan in plans_dicts:
            eng.copy(plan["source"], plan["destination"])

    put_calls = mock_session_put.call_args_list
    assert len(put_calls) == total_chunks, (
        f"Expected {total_chunks} PUT calls, got {len(put_calls)}"
    )

    get_call_count = mock_sharepoint_gets.call_count
    assert get_call_count == 2 + (file_count * 2)

    uploaded_chunks = [call.kwargs["data"] for call in put_calls]
    offset = 0
    for expected_payload, chunk_count in zip(
        expected_payloads, chunk_counts, strict=True
    ):
        uploaded_payload = b"".join(uploaded_chunks[offset : offset + chunk_count])
        assert uploaded_payload == expected_payload, "Payload mismatch"
        offset += chunk_count


def _assert_s3_object_absent(s3: boto3.client, bucket: str, key: str) -> None:
    """Assert that an S3 object does not exist."""
    with pytest.raises(ClientError):
        s3.get_object(Bucket=bucket, Key=key)


def test_e2e_write_to_s3_validation_failure_raises_and_writes_nothing(
    s3: boto3.client,
) -> None:
    """A missing SharePoint source aborts copy before anything is written to S3."""
    sp_site = utils.SP_SITE
    sp_library = utils.SP_LIBRARY
    s3_bucket = "my-destination-bucket"
    source = "reports/2026/missing.csv"
    destination = "path/to/missing.csv"

    utils.create_bucket(s3_bucket, s3)

    get_mocks = [
        utils.mock_site_id_response(),
        utils.mock_drive_id_response("complete"),
        utils.build_response(status_code=404, json_body={}),
    ]

    with (
        patch(
            "aws_sharepoint_connector.auth.ClientSecretCredential.get_token",
            side_effect=utils.mock_get_token,
        ),
        patch(
            "aws_sharepoint_connector.sharepoint.requests.get", side_effect=get_mocks
        ),
    ):
        eng = create_engine("write_to_s3", sp_site, sp_library, s3_bucket)
        with pytest.raises(ProcessingError, match="Validation failed"):
            eng.copy(source, destination)

    _assert_s3_object_absent(s3, s3_bucket, destination)


def test_e2e_write_to_s3_mid_batch_failure_preserves_prior_and_stops(
    s3: boto3.client,
) -> None:
    """A mid-batch failure keeps the first transfer and blocks the failing one."""
    sp_site = utils.SP_SITE
    sp_library = utils.SP_LIBRARY
    s3_bucket = "my-destination-bucket"

    plans = [
        {"source": "reports/2026/file1.csv", "destination": "path/to/file1.csv"},
        {"source": "reports/2026/file2.csv", "destination": "path/to/file2.csv"},
    ]
    payload_one = create_test_data(1)

    utils.create_bucket(s3_bucket, s3)

    get_mocks = [
        utils.mock_site_id_response(),
        utils.mock_drive_id_response("complete"),
        utils.mock_check_object_response(200, "file1.csv", "file"),
        build_binary_response(payload_one),
        utils.build_response(status_code=404, json_body={}),
    ]

    with (
        patch(
            "aws_sharepoint_connector.auth.ClientSecretCredential.get_token",
            side_effect=utils.mock_get_token,
        ),
        patch(
            "aws_sharepoint_connector.sharepoint.requests.get", side_effect=get_mocks
        ),
    ):
        eng = create_engine("write_to_s3", sp_site, sp_library, s3_bucket)

        eng.copy(plans[0]["source"], plans[0]["destination"])

        with pytest.raises(ProcessingError, match="Validation failed"):
            eng.copy(plans[1]["source"], plans[1]["destination"])

    stored = s3.get_object(Bucket=s3_bucket, Key=plans[0]["destination"])
    assert stored["Body"].read() == payload_one
    _assert_s3_object_absent(s3, s3_bucket, plans[1]["destination"])


def test_e2e_write_to_sharepoint_validation_failure_raises_and_uploads_nothing(
    s3: boto3.client,
) -> None:
    """A missing S3 source aborts copy before any SharePoint upload occurs."""
    sp_site = utils.SP_SITE
    sp_library = utils.SP_LIBRARY
    s3_bucket = utils.S3_BUCKET
    source = "path/to/missing.csv"
    destination = "reports/2026/missing.csv"

    utils.create_bucket(s3_bucket, s3)

    get_mocks = [
        utils.mock_site_id_response(),
        utils.mock_drive_id_response("complete"),
        utils.mock_check_object_response(200, "reports/2026", "folder"),
    ]

    with (
        patch(
            "aws_sharepoint_connector.auth.ClientSecretCredential.get_token",
            side_effect=utils.mock_get_token,
        ),
        patch(
            "aws_sharepoint_connector.sharepoint.requests.get", side_effect=get_mocks
        ),
        patch("aws_sharepoint_connector.sharepoint.requests.post") as mock_post,
        patch("aws_sharepoint_connector.sharepoint.requests.Session.put") as mock_put,
    ):
        eng = create_engine("write_to_sharepoint", sp_site, sp_library, s3_bucket)
        with pytest.raises(ProcessingError, match="Validation failed"):
            eng.copy(source, destination)

    mock_post.assert_not_called()
    mock_put.assert_not_called()


@pytest.mark.parametrize(
    ("source", "destination", "archive_folder", "source_handling"),
    [
        ("../secrets.csv", "path/to/file.csv", "", "none"),
        ("reports/2026/file.csv", "/abs/path.csv", "", "none"),
        ("reports/2026/file.csv", "path/to/file.csv", "../escape", "archive"),
    ],
)
def test_e2e_copy_rejects_unsafe_paths(
    source: str,
    destination: str,
    archive_folder: str,
    source_handling: str,
    s3: boto3.client,
) -> None:
    """Copy rejects traversal/absolute paths before any network interaction."""
    utils.create_bucket("my-destination-bucket", s3)

    with (
        patch(
            "aws_sharepoint_connector.auth.ClientSecretCredential.get_token",
            side_effect=utils.mock_get_token,
        ),
        patch(
            "aws_sharepoint_connector.sharepoint.requests.get",
            side_effect=[
                utils.mock_site_id_response(),
                utils.mock_drive_id_response("complete"),
            ],
        ),
    ):
        eng = create_engine(
            "write_to_s3", utils.SP_SITE, utils.SP_LIBRARY, "my-destination-bucket"
        )
        with pytest.raises(InvalidPathError):
            eng.copy(
                source,
                destination,
                archive_folder=archive_folder,
                source_handling=source_handling,  # type: ignore[arg-type]
            )
