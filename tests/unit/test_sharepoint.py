"""Unit tests for the sharepoint module."""

import logging
from io import BytesIO
from unittest.mock import patch

import pytest
import requests

from connector.config import SecretConfig, SharePointLibrary
from connector.exceptions import UploadError
from connector.sharepoint import SharePointConnector
from tests import test_utils as utils

SP_SITE = utils.SP_SITE  # "analytics-site"
SP_LIBRARY = utils.SP_LIBRARY  # "Documents"
SP_FILE_PATH = utils.SP_FILE_PATH  # "reports/2026/file1.csv"
SP_FILE_NAME = utils.SP_FILE_NAME  # "file1.csv"
SP_FILE_PATH_NO_DIR = "file6.csv"

# Expected base URL after update_with_file_path(SP_FILE_PATH)
EXPECTED_BASE_URL = (
    "https://graph.microsoft.com/v1.0/drives/fake-drive-id"
    "/root:/reports/2026/file1.csv:"
)


def make_connector(
    secrets: SecretConfig | None = None,
    library: SharePointLibrary | None = None,
) -> SharePointConnector:
    """Create a SharePointConnector with patched HTTP calls."""
    return SharePointConnector(
        secrets=secrets or SecretConfig(),  # type: ignore[call-arg]
        library=library or utils.make_sharepoint_library(),
    )


def test_sharepoint_connector_initialization() -> None:
    """Test that SharePointConnector sets up headers and drive_id on init."""
    secrets = SecretConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_patches():
        connector = make_connector(secrets)

    assert connector.headers == {
        "Authorization": "Bearer fake-token",
        "Accept": "application/json",
    }
    assert connector.drive_id == "fake-drive-id"
    assert connector.file_path == ""
    assert connector.base_url == ""


def test_set_graph_headers() -> None:
    """Test that set_graph_headers populates the correct auth headers."""
    secrets = SecretConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_patches():
        connector = make_connector(secrets)
        connector.set_graph_headers()

    assert connector.headers == {
        "Authorization": "Bearer fake-token",
        "Accept": "application/json",
    }


def test_get_site_id_success() -> None:
    """Test that get_site_id returns the site id and calls the correct URL."""
    secrets = SecretConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_patches():
        connector = make_connector(secrets)

    with patch(
        "connector.sharepoint.requests.get",
        return_value=utils.mock_site_id_response(),
    ) as mock_get:
        site_id = connector.get_site_id()

    assert site_id == "fake-site-id"
    assert mock_get.call_count == 1
    assert mock_get.call_args[0][0] == (
        "https://graph.microsoft.com/v1.0/sites/"
        "justiceuk.sharepoint.com:/sites/analytics-site"
    )
    assert mock_get.call_args[1]["headers"] == {
        "Authorization": "Bearer fake-token",
        "Accept": "application/json",
    }


def test_get_site_id_missing_id_raises() -> None:
    """Test that get_site_id raises UploadError when Graph omits 'id'."""
    secrets = SecretConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_patches():
        connector = make_connector(secrets)

    with (
        patch(
            "connector.sharepoint.requests.get",
            return_value=utils.build_response(status_code=200, json_body={}),
        ),
        pytest.raises(UploadError, match="no site ID"),
    ):
        connector.get_site_id()


@pytest.mark.parametrize(
    "exception",
    [
        requests.HTTPError("Mock HTTP error"),
        ValueError("Mock value error"),
    ],
)
def test_set_drive_id_error(exception: Exception) -> None:
    """Test that set_drive_id raises UploadError when drive retrieval fails."""
    secrets = SecretConfig()  # type: ignore[call-arg]

    with (
        utils.sharepoint_connector_patches(),
        patch(
            "connector.sharepoint.SharePointConnector.get_site_id",
            side_effect=exception,
        ),
        pytest.raises(UploadError),
    ):
        make_connector(secrets)


def test_update_with_file_path_sets_file_path_and_base_url() -> None:
    """Test that update_with_file_path stores path and derives base_url."""
    secrets = SecretConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_patches():
        connector = make_connector(secrets)

    connector.update_with_file_path(SP_FILE_PATH)

    assert connector.file_path == SP_FILE_PATH
    assert connector.base_url == EXPECTED_BASE_URL


def test_set_base_url_encodes_path() -> None:
    """Test that set_base_url constructs the expected Graph API base URL."""
    secrets = SecretConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_patches():
        connector = make_connector(secrets)

    connector.update_with_file_path(SP_FILE_PATH)
    connector.set_base_url()

    assert connector.base_url == EXPECTED_BASE_URL


def test_set_upload_url() -> None:
    """Test that set_upload_url stores the correct upload URL."""
    secrets = SecretConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_patches():
        connector = make_connector(secrets)

    connector.update_with_file_path(SP_FILE_PATH)

    with patch(
        "connector.sharepoint.requests.post",
        return_value=utils.mock_upload_url_response(),
    ) as mock_post:
        connector.set_upload_url()

    assert connector.upload_url == "https://fake-upload-url"
    assert mock_post.call_count == 1
    assert mock_post.call_args[0][0] == (
        "https://graph.microsoft.com/v1.0/drives/fake-drive-id"
        "/root:/reports/2026/file1.csv:/createUploadSession"
    )
    assert mock_post.call_args[1]["headers"] == {
        "Authorization": "Bearer fake-token",
        "Accept": "application/json",
    }
    assert mock_post.call_args[1]["json"] == {
        "item": {
            "@microsoft.graph.conflictBehavior": "replace",
            "name": "file1.csv",
        }
    }


def test_set_download_url() -> None:
    """Test that set_download_url builds the correct content URL."""
    secrets = SecretConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_patches():
        connector = make_connector(secrets)

    connector.update_with_file_path(SP_FILE_PATH)
    connector.set_download_url()

    assert connector.download_url == (
        "https://graph.microsoft.com/v1.0/drives/fake-drive-id"
        "/root:/reports/2026/file1.csv:/content"
    )


def test_fetch_file_success() -> None:
    """Test that fetch_file returns the response bytes."""
    secrets = SecretConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_patches():
        connector = make_connector(secrets)

    connector.update_with_file_path(SP_FILE_PATH)
    connector.set_download_url()

    with patch(
        "connector.sharepoint.requests.get",
        return_value=utils.mock_fetch_file_response(200),
    ):
        data = connector.fetch_file()

    assert data == b'{"content": "fake-file-content"}'


def test_fetch_file_not_found() -> None:
    """Test that fetch_file raises UploadError when the file is missing."""
    secrets = SecretConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_patches():
        connector = make_connector(secrets)

    connector.update_with_file_path(SP_FILE_PATH)
    connector.set_download_url()

    with (
        patch(
            "connector.sharepoint.requests.get",
            return_value=utils.mock_fetch_file_response(404),
        ),
        pytest.raises(UploadError, match="File not found in SharePoint"),
    ):
        connector.fetch_file()


def test_fetch_file_request_error() -> None:
    """Test that fetch_file raises UploadError on request errors."""
    secrets = SecretConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_patches():
        connector = make_connector(secrets)

    connector.update_with_file_path(SP_FILE_PATH)
    connector.set_download_url()

    with (
        patch(
            "connector.sharepoint.requests.get",
            side_effect=requests.RequestException("Mock request error"),
        ),
        pytest.raises(UploadError, match="Failed to fetch file from SharePoint"),
    ):
        connector.fetch_file()


@pytest.mark.parametrize(
    ("file_path", "expected_verify_url"),
    [
        (
            SP_FILE_PATH,
            "https://graph.microsoft.com/v1.0/drives/fake-drive-id"
            "/root:/reports/2026/file1.csv:?$select=name,size,file",
        ),
        (
            SP_FILE_PATH_NO_DIR,
            "https://graph.microsoft.com/v1.0/drives/fake-drive-id"
            "/root:/file6.csv:?$select=name,size,file",
        ),
    ],
)
def test_verify_uploaded_file_success(
    file_path: str,
    expected_verify_url: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that verify_uploaded_file succeeds when the uploaded file is present."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    expected_size = 13
    file_name = file_path.split("/")[-1]

    with utils.sharepoint_connector_patches():
        connector = make_connector(secrets)

    connector.update_with_file_path(file_path)

    with (
        patch(
            "connector.sharepoint.requests.get",
            return_value=utils.mock_verify_uploaded_file_response(
                200, file_name, expected_size
            ),
        ) as mock_verify,
        caplog.at_level(logging.INFO, logger="s3-sharepoint"),
    ):
        connector.verify_uploaded_file(expected_size=expected_size)

    assert (
        f"Verified uploaded file '{file_name}' ({expected_size} bytes)" in caplog.text
    )
    assert mock_verify.call_count == 1
    assert mock_verify.call_args[0][0] == expected_verify_url
    assert mock_verify.call_args[1]["headers"] == {
        "Authorization": "Bearer fake-token",
        "Accept": "application/json",
    }


def test_verify_uploaded_not_found() -> None:
    """Test that verify_uploaded_file raises UploadError when the file is absent."""
    secrets = SecretConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_patches():
        connector = make_connector(secrets)

    connector.update_with_file_path(SP_FILE_PATH)

    with (
        patch(
            "connector.sharepoint.requests.get",
            return_value=utils.build_response(status_code=404),
        ),
        pytest.raises(UploadError, match="Verification failed"),
    ):
        connector.verify_uploaded_file(expected_size=12)


def test_verify_uploaded_size_mismatch() -> None:
    """Test that verify_uploaded_file raises UploadError when size does not match."""
    secrets = SecretConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_patches():
        connector = make_connector(secrets)

    connector.update_with_file_path(SP_FILE_PATH)

    with (
        patch(
            "connector.sharepoint.requests.get",
            return_value=utils.build_response(
                status_code=200,
                json_body={"name": SP_FILE_NAME, "size": 999, "file": {}},
            ),
        ),
        pytest.raises(UploadError, match="Verification failed"),
    ):
        connector.verify_uploaded_file(expected_size=12)


def test_upload_stream_in_chunks_success() -> None:
    """Test that a small payload is uploaded in a single chunk."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    payload = b"chunk-content"

    with (
        utils.sharepoint_connector_patches(
            extra_post_side_effects=[utils.mock_upload_url_response()],
            extra_get_side_effects=[
                utils.mock_verify_uploaded_file_response(
                    200, SP_FILE_NAME, len(payload)
                ),
            ],
        ),
        patch(
            "connector.sharepoint.requests.Session.get",
            return_value=utils.mock_get_next_start_response(0, len(payload)),
        ),
        patch(
            "connector.sharepoint.requests.Session.put",
            return_value=utils.mock_session_put_response(),
        ) as mock_put,
    ):
        connector = make_connector(secrets)
        connector.update_with_file_path(SP_FILE_PATH)
        connector.set_upload_url()
        connector.upload_stream_in_chunks(BytesIO(payload), len(payload))

    assert mock_put.call_count == 1
    assert mock_put.call_args[1]["data"] == payload


def test_upload_stream_in_chunks_permanent_error_raises() -> None:
    """Test that a 400-range (non-429) response aborts the upload."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    payload = b"chunk-content"

    with (
        utils.sharepoint_connector_patches(
            extra_post_side_effects=[utils.mock_upload_url_response()],
        ),
        patch(
            "connector.sharepoint.requests.Session.get",
            return_value=utils.mock_get_next_start_response(0, len(payload)),
        ),
        patch(
            "connector.sharepoint.requests.Session.put",
            return_value=utils.mock_session_put_response(status_code=403),
        ),
    ):
        connector = make_connector(secrets)
        connector.update_with_file_path(SP_FILE_PATH)
        connector.set_upload_url()
        with pytest.raises(UploadError, match="permanent HTTP 403"):
            connector.upload_stream_in_chunks(BytesIO(payload), len(payload))


def test_upload_stream_in_chunks_exceeds_retries_raises() -> None:
    """Test that exceeding MAX_CHUNK_RETRIES raises UploadError."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    payload = b"chunk-content"

    with (
        utils.sharepoint_connector_patches(
            extra_post_side_effects=[utils.mock_upload_url_response()],
        ),
        patch(
            "connector.sharepoint.requests.Session.get",
            return_value=utils.mock_get_next_start_response(0, len(payload)),
        ),
        patch(
            "connector.sharepoint.requests.Session.put",
            side_effect=requests.exceptions.RequestException("network error"),
        ),
    ):
        connector = make_connector(secrets)
        connector.update_with_file_path(SP_FILE_PATH)
        connector.set_upload_url()
        with pytest.raises(UploadError, match="retries"):
            connector.upload_stream_in_chunks(BytesIO(payload), len(payload))
