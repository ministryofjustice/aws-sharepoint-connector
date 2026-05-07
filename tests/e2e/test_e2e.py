"""E2E tests for run() function: test writing to S3 and SharePoint."""

from math import ceil
from unittest.mock import patch

import boto3
import pytest
from requests import Response

from connector.config import S3ToSPMovementPlan, SPToS3MovementPlan
from connector.main import run
from tests import test_utils as utils


def create_test_data(size_mb: int) -> bytes:
    """Create deterministic test data of a specific size in MB."""
    return bytes([i % 256 for i in range(size_mb * 1024 * 1024)])


def build_binary_response(content: bytes) -> Response:
    """Create a binary response for SharePoint file download."""
    response = Response()
    response.status_code = 200
    response._content = content
    response.headers["Content-Type"] = "application/octet-stream"
    return response


@pytest.mark.parametrize("file_count", [1, 6])
def test_e2e_write_to_s3_single_and_batch(file_count: int, s3: boto3.client) -> None:
    """Test write_to_s3 with 1 file and 6 files."""
    plans_dicts, _ = utils.create_sp_to_s3_movement_plan()

    # Select plans based on file count
    selected_plans_dicts = plans_dicts[:file_count]
    selected_plans = [SPToS3MovementPlan(**p) for p in selected_plans_dicts]  # type: ignore

    for plan in selected_plans:
        if plan.s3_bucket not in [b["Name"] for b in s3.list_buckets()["Buckets"]]:
            s3.create_bucket(
                Bucket=plan.s3_bucket,
                CreateBucketConfiguration={"LocationConstraint": "eu-west-2"},
            )

    file_sizes_mb = [1] * file_count
    expected_payloads = [create_test_data(size) for size in file_sizes_mb]

    # Mock SharePoint GET responses in order:
    # - For each file: site_id → drive_id → ensure_folder → download (4 responses)
    get_mocks: list = []
    for i in range(file_count):
        # Use factory functions to create fresh Response objects
        get_mocks.append(utils.mock_site_id_response())
        get_mocks.append(utils.mock_drive_id_response("complete"))
        get_mocks.append(utils.mock_ensure_destination_folder_response("folder"))
        get_mocks.append(build_binary_response(expected_payloads[i]))

    with (
        patch(
            "connector.auth.ClientSecretCredential.get_token",
            side_effect=utils.mock_get_token,
        ),
        patch("connector.sharepoint.requests.get", side_effect=get_mocks),
    ):
        run(mode="write_to_s3", data_movement_plan=selected_plans_dicts)

    for plan, expected_payload in zip(selected_plans, expected_payloads):
        obj = s3.get_object(Bucket=plan.s3_bucket, Key=plan.s3_file_key)
        actual_payload = obj["Body"].read()
        assert (
            actual_payload == expected_payload
        ), f"Data mismatch for {plan.s3_file_key}"


@pytest.mark.parametrize("file_count", [1, 6])
def test_e2e_write_to_sharepoint_single_and_batch(
    file_count: int, s3: boto3.client
) -> None:
    """Test write_to_sharepoint with 1 file and 6 files."""
    plans_dicts, _ = utils.create_s3_to_sp_movement_plan()

    selected_plans_dicts = plans_dicts[:file_count]
    selected_plans = [S3ToSPMovementPlan(**p) for p in selected_plans_dicts]  # type: ignore

    file_sizes_mb = [1] * file_count
    expected_payloads = [create_test_data(size) for size in file_sizes_mb]

    for plan in selected_plans:
        if plan.s3_bucket not in [b["Name"] for b in s3.list_buckets()["Buckets"]]:
            s3.create_bucket(
                Bucket=plan.s3_bucket,
                CreateBucketConfiguration={"LocationConstraint": "eu-west-2"},
            )

    for plan, payload in zip(selected_plans, expected_payloads):
        s3.put_object(Bucket=plan.s3_bucket, Key=plan.s3_file_key, Body=payload)

    # Build GET mock responses.
    # For each file: setup (site_id, drive_id, ensure_folder) + verify
    get_mocks: list = []
    for i in range(file_count):
        size_mb = file_sizes_mb[i]
        get_mocks.append(utils.mock_site_id_response())
        get_mocks.append(utils.mock_drive_id_response("complete"))
        get_mocks.append(utils.mock_ensure_destination_folder_response("folder"))
        get_mocks.append(
            utils.mock_verify_uploaded_file_response(
                200, f"file{i+1}.csv", size_mb * 1024 * 1024
            )
        )

    post_mocks = [utils.mock_upload_url_response() for _ in range(file_count)]

    chunk_counts = [
        ceil((size * 1024 * 1024) / (10 * 1024 * 1024)) for size in file_sizes_mb
    ]
    total_chunks = sum(chunk_counts)

    with (
        patch(
            "connector.auth.ClientSecretCredential.get_token",
            side_effect=utils.mock_get_token,
        ),
        patch("connector.sharepoint.requests.get", side_effect=get_mocks),
        patch("connector.sharepoint.requests.post", side_effect=post_mocks),
        patch(
            "connector.sharepoint.requests.Session.get",
            side_effect=[
                utils.mock_get_next_start_response() for _ in range(file_count)
            ],
        ),
        patch(
            "connector.sharepoint.requests.Session.put",
            side_effect=[
                utils.mock_session_put_response() for _ in range(total_chunks)
            ],
        ) as mock_session_put,
    ):
        run(mode="write_to_sharepoint", data_movement_plan=selected_plans_dicts)

    put_calls = mock_session_put.call_args_list
    assert (
        len(put_calls) == total_chunks
    ), f"Expected {total_chunks} PUT calls, got {len(put_calls)}"

    put_data_by_call = [call.kwargs["data"] for call in put_calls]
    start = 0
    for expected_payload, chunk_count in zip(
        expected_payloads, chunk_counts, strict=True
    ):
        end = start + chunk_count
        uploaded_payload = b"".join(put_data_by_call[start:end])
        assert uploaded_payload == expected_payload, f"Payload mismatch"
        start = end
