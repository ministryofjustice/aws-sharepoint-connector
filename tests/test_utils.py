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

from connector.config import S3Bucket, SharePointLibrary

SP_SITE = "analytics-site"
SP_LIBRARY = "Documents"
SP_FILE_PATH = "reports/2026/file1.csv"
SP_FILE_NAME = "file1.csv"
S3_BUCKET = "my-source-bucket"
S3_KEY = "path/to/file1.csv"


def make_sharepoint_library(
    site: str = SP_SITE,
    library: str = SP_LIBRARY,
) -> SharePointLibrary:
    """Return a SharePointLibrary instance for tests."""
    return SharePointLibrary(site=site, library=library)


def make_s3_bucket(bucket: str = S3_BUCKET) -> S3Bucket:
    """Return an S3Bucket instance for tests."""
    return S3Bucket(bucket=bucket)


def create_bucket(bucket_name: str, s3: boto3.client) -> None:
    """Create a mocked S3 bucket in eu-west-2."""
    s3.create_bucket(
        Bucket=bucket_name,
        CreateBucketConfiguration={"LocationConstraint": "eu-west-2"},
    )


def build_response(
    *,
    status_code: int = 200,
    json_body: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> Response:
    """Return a realistic requests.Response for unit tests."""
    response = Response()
    response.status_code = status_code
    response._content = json.dumps(json_body).encode("utf-8")
    response.headers["Content-Type"] = "application/json"
    return response


def mock_get_token(_: str) -> AccessToken:
    """Mock get_token for ClientSecretCredential."""
    return AccessToken(
        token="fake-token",  # noqa: S106  # nosec: B106
        expires_on=9999999999,
    )


def mock_drive_id_response(
    content: Literal["complete", "no_drives", "no_value"],
) -> Response:
    """Mock response for Graph drives lookup."""
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


def mock_token_response() -> Response:
    """Mock response for get_azure_token."""
    return build_response(json_body={"access_token": "fake-token", "expires_in": 3600})


def mock_site_id_response() -> Response:
    """Mock response for get_site_id."""
    return build_response(json_body={"id": "fake-site-id"})


def mock_upload_url_response() -> Response:
    """Mock response for createUploadSession."""
    return build_response(json_body={"uploadUrl": "https://fake-upload-url"})


def mock_session_put_response(status_code: int = 200) -> Response:
    """Mock response for requests.Session.put."""
    return build_response(status_code=status_code)


def mock_fetch_file_response(status_code: int) -> Response:
    """Mock response for fetch_file."""
    return build_response(
        json_body={"content": "fake-file-content"}, status_code=status_code
    )


def mock_verify_uploaded_file_response(
    status_code: int,
    file_name: str,
    size: int = 0,
) -> Response:
    """Mock response for verify_uploaded_file."""
    return build_response(
        json_body={"name": file_name, "size": size, "file": {}},
        status_code=status_code,
    )


def mock_get_next_start_response(start: int = 0, end: int = 10) -> Response:
    """Mock response for get_next_start."""
    return build_response(json_body={"nextExpectedRanges": [f"{start}-{end}"]})


def mock_check_file_response(status_code: int, file_name: str) -> Response:
    """Mock response for check_file_exists — returns a file item metadata response."""
    return build_response(
        json_body={"name": file_name, "file": {}},
        status_code=status_code,
    )


def mock_check_folder_response(status_code: int, folder_name: str) -> Response:
    """Mock response for check_folder_exists — returns a folder metadata response."""
    return build_response(
        json_body={"name": folder_name, "folder": {"childCount": 0}},
        status_code=status_code,
    )


@contextmanager
def sharepoint_connector_patches(
    extra_post_side_effects: list[Response] | None = None,
    extra_get_side_effects: list[Response] | None = None,
    num_connectors: int = 1,
) -> Generator[tuple[Mock, Mock, Mock], Any, Any]:
    """Mock SharePointConnector internals to avoid real API calls.

    SharePointConnector.__init__ issues exactly two GET requests:
      1. get_site_id()      — one GET to the Graph sites endpoint.
      2. auth.get_drive_id() — one GET to the site drives endpoint.

    Args:
        extra_post_side_effects: Additional POST responses appended after setup.
        extra_get_side_effects: Additional GET responses appended after setup
            (e.g. fetch_file or verify_uploaded_file responses).
        num_connectors: Number of SharePointConnector instances expected to be
            created. Multiplies the two setup GET responses accordingly.

    """
    post_side_effects: list[Response] = list(extra_post_side_effects or [])

    get_side_effects: list[Response] = []
    for _ in range(num_connectors):
        get_side_effects.append(mock_site_id_response())
        get_side_effects.append(mock_drive_id_response("complete"))

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
    """Return a simple DataFrame to use as test CSV content."""
    return pd.DataFrame(
        {
            "Column1": ["Value1", "Value2", "Value3"],
            "Column2": [10, 20, 30],
            "Column3": ["A", "B", "C"],
        }
    )
