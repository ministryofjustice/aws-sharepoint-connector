"""Utility functions and fixtures for unit tests."""

import json
import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, Literal
from unittest.mock import patch

import boto3
import pandas as pd
from azure.core.credentials import AccessToken
from requests import Response

from connector.config import AppConfig


def create_bucket(bucket_name: str, s3: boto3.client) -> None:
    """Create a mocked s3 bucket."""
    s3.create_bucket(
        Bucket=bucket_name,
        CreateBucketConfiguration={"LocationConstraint": "eu-west-2"},
    )


def create_test_config(
    mode: str = "write_to_s3", sp_folder_path: str = "fake-folder-path"
) -> AppConfig:
    """Fixture to provide a sample configuration for tests."""
    os.environ["SECRET_AZURE_TENANT_ID"] = "12345678901234567890123456789012"  # noqa: S105
    os.environ["SECRET_AZURE_CLIENT_ID"] = "fake-client-id"  # noqa: S105
    os.environ["SECRET_AZURE_CLIENT_SECRET"] = (
        "fake-client-secret"  # pragma: allowlist secret # noqa: S105
    )
    os.environ["SP_SITE_NAME"] = "fake-site-name"
    os.environ["SP_LIBRARY_NAME"] = "Documents"
    os.environ["SP_FOLDER_PATH"] = sp_folder_path
    os.environ["SP_FILE_NAME"] = "fake-file.csv"
    os.environ["S3_BUCKET"] = "fake-bucket"
    os.environ["FILE_KEY"] = "directory/fake-file.csv"
    os.environ["MODE"] = mode

    return AppConfig()  # type: ignore[call-arg]


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
    return AccessToken(token="fake-token", expires_on=9999999999)  # noqa: S106


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
        json_body={
            "folder": [] if content == "folder" else None,
            "file": [] if content == "no_folder" else None,
        },
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


def mock_fetch_file_response(status_code: int) -> Response:
    """Mock response for the fetch_file function."""
    return build_response(
        json_body={"content": "fake-file-content"}, status_code=status_code
    )


def mock_verify_uploaded_file_response(status_code: int, file_name: str) -> Response:
    """Mock response for the verify_uploaded_file function."""
    return build_response(
        json_body={"value": [{"name": file_name}, {"name": "other-file"}]},
        status_code=status_code,
    )


def mock_get_next_start_response(start: int = 0, end: int = 10) -> Response:
    """Mock response for the get_next_start function."""
    return build_response(json_body={"nextExpectedRanges": [f"{start}-{end}"]})


@contextmanager
def sharepoint_connector_init_patches() -> Generator[Any, Any, Any]:
    """Mock the underlying methods of SharePointConnector to avoid real API calls."""
    with (
        patch(
            "connector.auth.ClientSecretCredential.get_token",
            side_effect=mock_get_token,
        ) as mock_token,
        patch(
            "connector.sharepoint.requests.get",
            side_effect=[
                mock_site_id_response(),
                mock_drive_id_response("complete"),
                mock_ensure_destination_folder_response("folder"),
            ],
        ) as mock_get,
        patch(
            "connector.sharepoint.requests.post",
            return_value=mock_upload_url_response(),
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
