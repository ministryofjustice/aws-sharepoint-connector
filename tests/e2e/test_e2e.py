"""E2E tests for uploading from S3 to SharePoint with mocked Graph API calls."""

from math import ceil
from unittest.mock import patch

import boto3
import pytest
from requests import Response

from connector import engine
from connector.config import AppConfig
from tests import test_utils as utils


def create_test_data(file_size: int) -> bytes:
    """Create deterministic test data of a specific size in MB."""
    return bytes([i % 256 for i in range(file_size * 1024 * 1024)])


def build_binary_response(content: bytes, status_code: int = 200) -> Response:
    """Create a realistic binary response object for SharePoint content download."""
    response = Response()
    response.status_code = status_code
    response._content = content
    response.headers["Content-Type"] = "application/octet-stream"
    return response


# Ordered request reference for MODE=write_to_sharepoint.
REQUEST_CALL_ORDER = [
    "requests.get -> get_site_id(site_url)",
    "requests.get -> auth.get_drive_id(drives_url)",
    "requests.get -> ensure_destination_folder(folder_meta_url)",
    "requests.post -> create_upload_url(createUploadSession)",
    "Session.get -> get_next_start(upload_url)",
    "Session.put -> put_chunk(upload_url) [repeats per chunk]",
    "requests.get -> verify_uploaded_file(children_url)",
]


@pytest.mark.parametrize(
    ("num_files", "file_sizes"),
    [
        (1, [1]),
        (1, [10]),
        (1, [100]),
        (3, [1, 10, 100]),
    ],
)
def test_e2e_write_to_sharepoint(
    num_files: int, file_sizes: list[int], s3: boto3.client
) -> None:
    """Run upload flow with mocked requests.get/put and Session.get/put side effects."""
    config = AppConfig()  # type: ignore[call-arg]
    utils.create_bucket(config.S3_BUCKET, s3)

    chunk_counts = [
        ceil((size_mb * 1024 * 1024) / (10 * 1024 * 1024)) for size_mb in file_sizes
    ]
    total_chunk_put_calls = sum(chunk_counts)

    extra_post_side_effects = [
        utils.mock_upload_url_response() for _ in range(num_files)
    ]
    expected_payloads = [create_test_data(file_size_mb) for file_size_mb in file_sizes]
    extra_get_side_effects = [
        utils.mock_verify_uploaded_file_response(
            200,
            config.SP_FILE_NAME,
            len(expected_payload),
        )
        for expected_payload in expected_payloads
    ]

    with (
        utils.sharepoint_connector_patches(
            extra_post_side_effects=extra_post_side_effects,
            extra_get_side_effects=extra_get_side_effects,
        ) as (_, mock_get, mock_post),
        patch(
            "connector.sharepoint.requests.Session.get",
            side_effect=[
                utils.mock_get_next_start_response() for _ in range(num_files)
            ],
        ) as mock_session_get,
        patch(
            "connector.sharepoint.requests.Session.put",
            side_effect=[
                utils.mock_session_put_response() for _ in range(total_chunk_put_calls)
            ],
        ) as mock_session_put,
    ):
        eng = engine.UploadToSharePointEngine(config)

        for data in expected_payloads:
            s3.put_object(Bucket=config.S3_BUCKET, Key=config.FILE_KEY, Body=data)
            content = eng.download_file()
            eng.upload_file(content)

    assert mock_post.call_count == num_files
    assert mock_get.call_count == 3 + num_files
    assert mock_session_get.call_count == num_files
    assert mock_session_put.call_count == total_chunk_put_calls

    # Validate that each uploaded payload equals the original per-file data.
    put_data_by_call = [call.kwargs["data"] for call in mock_session_put.call_args_list]
    start = 0
    for expected_payload, chunk_count in zip(
        expected_payloads, chunk_counts, strict=True
    ):
        end = start + chunk_count
        uploaded_payload = b"".join(put_data_by_call[start:end])
        assert uploaded_payload == expected_payload
        start = end


@pytest.mark.parametrize(
    ("num_files", "file_sizes"),
    [
        (1, [1]),
        (1, [10]),
        (1, [100]),
        (3, [1, 10, 100]),
    ],
)
def test_e2e_write_to_s3(
    num_files: int, file_sizes: list[int], s3: boto3.client
) -> None:
    """Run SharePoint to S3 flow with patched SharePoint GET responses."""
    config = AppConfig()  # type: ignore[call-arg]
    utils.create_bucket(config.S3_BUCKET, s3)

    expected_payloads = [create_test_data(file_size_mb) for file_size_mb in file_sizes]

    with utils.sharepoint_connector_patches(
        extra_get_side_effects=[
            build_binary_response(payload) for payload in expected_payloads
        ],
    ) as (_, mock_get, mock_post):
        eng = engine.UploadToS3Engine(config)

        for expected_payload in expected_payloads:
            content = eng.download_file()
            assert content == expected_payload

            eng.upload_file(content)
            uploaded = s3.get_object(Bucket=config.S3_BUCKET, Key=config.FILE_KEY)
            assert uploaded["Body"].read() == expected_payload

    assert mock_post.call_count == 0
    assert mock_get.call_count == 3 + num_files
