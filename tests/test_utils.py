"""Utility functions and fixtures for unit tests."""

import json
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Literal
from unittest.mock import Mock, patch

import boto3
import pandas as pd
from azure.core.credentials import AccessToken
from requests import Response

from connector.config import DataMovementPlan, S3ToSPMovementPlan, SPToS3MovementPlan


def create_s3_to_sp_movement_plan() -> tuple[
    list[dict[str, dict[str, str]]], DataMovementPlan
]:
    """Return a sample S3 to SharePoint movement plan."""
    plans: list[dict[str, dict[str, str]]] = [
        {
            "source": {"bucket": "my-source-bucket", "key": f"path/to/file{i}.csv"},
            "destination": {
                "site": "analytics-site" if i < 3 else f"analytics-site-{(i % 2) + 1}",
                "library": "Documents",
                "directory": "reports/2026/" if i < 6 else "",
                "filename": f"file{i}.csv",
            },
        }
        for i in range(1, 7)
    ]

    plans[5]["destination"] = {k: v for k, v in plans[5]["destination"].items() if v}

    all_plans = [S3ToSPMovementPlan(**plan) for plan in plans]  # type: ignore[arg-type]
    return (plans, DataMovementPlan(data_to_move=all_plans))  # type: ignore[arg-type]


def create_sp_to_s3_movement_plan() -> tuple[
    list[dict[str, dict[str, str]]], DataMovementPlan
]:
    """Return a sample SharePoint to S3 movement plan."""
    plans: list[dict[str, dict[str, str]]] = [
        {
            "source": {
                "site": "analytics-site" if i < 2 or i == 3 else "analytics-site-2",
                "library": "Documents",
                "directory": "reports/2026/" if i < 6 else "",
                "filename": f"file{i}.csv",
            },
            "destination": {
                "bucket": (
                    "my-destination-bucket"
                    if i < 3
                    else f"my-destination-bucket-{(i % 2) + 1}"
                ),
                "key": f"path/to/file{i}.csv",
            },
        }
        for i in range(1, 7)
    ]
    # Remove directory for file6 if it was set to None
    plans[5]["source"] = {k: v for k, v in plans[5]["source"].items() if v is not None}

    all_plans = [SPToS3MovementPlan(**plan) for plan in plans]  # type: ignore[arg-type]
    return (plans, DataMovementPlan(data_to_move=all_plans))  # type: ignore[arg-type]


def create_bucket(bucket_name: str, s3: boto3.client) -> None:
    """Create a mocked s3 bucket."""
    s3.create_bucket(
        Bucket=bucket_name,
        CreateBucketConfiguration={"LocationConstraint": "eu-west-2"},
    )


def build_response(
    *,
    status_code: int = 200,
    json_body: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> Response:
    """Create a realistic requests.Response object for unit tests."""
    response = Response()
    response.status_code = status_code
    response._content = json.dumps(json_body).encode("utf-8")
    response.headers["Content-Type"] = "application/json"
    return response


def mock_get_token(_: str) -> AccessToken:
    """Mock get_token method of ClientSecretCredential."""
    return AccessToken(
        token="fake-token",  # noqa: S106  # nosec: B106
        expires_on=9999999999,
    )


def mock_drive_id_response(
    content: Literal["complete", "no_drives", "no_value"],
) -> Response:
    """Mock response for get_drive_id Graph drives lookup."""
    if content == "complete":
        return build_response(
            json_body={
                "value": [
                    {"name": "Documents", "id": "fake-drive-id"},
                    {"name": "Other Library", "id": "other-drive-id"},
                ]
            }
        )
    if content == "no_drives":
        return build_response(json_body={"value": []})
    return build_response(json_body={})


def mock_ensure_destination_folder_response(
    content: Literal["folder", "no_folder"], status_code: int = 200
) -> Response:
    """Mock response for the ensure_destination_folder method."""
    return build_response(
        json_body={"folder": []} if content == "folder" else {"file": []},
        status_code=status_code,
    )


def mock_token_response() -> Response:
    """Mock response for the get_azure_token function."""
    return build_response(json_body={"access_token": "fake-token", "expires_in": 3600})


def mock_site_id_response() -> Response:
    """Mock response for the get_site_id function."""
    return build_response(json_body={"id": "fake-site-id"})


def mock_upload_url_response() -> Response:
    """Mock response for the create_upload_url function."""
    return build_response(json_body={"uploadUrl": "https://fake-upload-url"})


def mock_session_put_response(status_code: int = 200) -> Response:
    """Mock response for the requests.session.put method."""
    return build_response(status_code=status_code)


def mock_fetch_file_response(status_code: int) -> Response:
    """Mock response for the fetch_file function."""
    return build_response(
        json_body={"content": "fake-file-content"}, status_code=status_code
    )


def mock_verify_uploaded_file_response(
    status_code: int,
    file_name: str,
    size: int = 0,
) -> Response:
    """Mock response for the verify_uploaded_file function."""
    return build_response(
        json_body={
            "value": [
                {"name": file_name, "size": size, "file": {}},
                {"name": "other-file", "size": 1, "file": {}},
            ]
        },
        status_code=status_code,
    )


def mock_get_next_start_response(start: int = 0, end: int = 10) -> Response:
    """Mock response for the get_next_start function."""
    return build_response(json_body={"nextExpectedRanges": [f"{start}-{end}"]})


@contextmanager
def sharepoint_connector_patches(
    extra_post_side_effects: list[Response] | None = None,
    extra_get_side_effects: list[Response] | None = None,
    num_files: int = 1,
) -> Generator[tuple[Mock, Mock, Mock], Any, Any]:
    """Mock the underlying methods of SharePointConnector to avoid real API calls.

    Args:
        extra_post_side_effects: Additional POST responses beyond the defaults.
        extra_get_side_effects: Additional GET responses (e.g., verify responses)
            beyond setup.
        num_files: Number of files being processed. Multiplies setup responses
            for each.

    """
    post_side_effects: list[Response] = []
    if extra_post_side_effects:
        post_side_effects.extend(extra_post_side_effects)

    # Build get_side_effects with setup responses (one set per file) + extra responses
    get_side_effects: list[Response] = []

    # Add setup response objects (one cycle per file)
    for _ in range(num_files):
        get_side_effects.append(mock_site_id_response())
        get_side_effects.append(mock_drive_id_response("complete"))
        get_side_effects.append(mock_ensure_destination_folder_response("folder"))

    # Add extra responses (verify, download, etc.)
    if extra_get_side_effects:
        get_side_effects.extend(extra_get_side_effects)

    with (
        patch(
            "connector.auth.ClientSecretCredential.get_token",
            side_effect=mock_get_token,
        ) as mock_token,
        patch(
            "connector.sharepoint.requests.get",
            side_effect=get_side_effects,
        ) as mock_get,
        patch(
            "connector.sharepoint.requests.post",
            side_effect=post_side_effects,
        ) as mock_post,
    ):
        yield mock_token, mock_get, mock_post


def create_test_csv() -> pd.DataFrame:
    """Create a simple DataFrame to use as test CSV content."""
    return pd.DataFrame(
        {
            "Column1": ["Value1", "Value2", "Value3"],
            "Column2": [10, 20, 30],
            "Column3": ["A", "B", "C"],
        }
    )
