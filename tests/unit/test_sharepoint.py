"""Unit tests for the sharepoint module."""

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
import requests

from connector.config import AppConfig
from connector.exceptions import UploadError
from connector.sharepoint import SharePointConnector
from tests import test_utils as utils


def test_sharepoint_connector_initialization() -> None:
    """Test that the SharePoint connector sets derived fields on init."""
    config = AppConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_init_patches():
        connector = SharePointConnector(config=config)

    assert connector.headers == {
        "Authorization": "Bearer fake-token",
        "Accept": "application/json",
    }
    assert connector.drive_id == "fake-drive-id"
    assert connector.file_path == "fake-folder-path/directory/fake-file.csv"
    assert connector.folder_path == "fake-folder-path/directory"
    assert (
        connector.base_url
        == "https://graph.microsoft.com/v1.0/drives/fake-drive-id/root:/fake-folder-path/directory/fake-file.csv:"
    )


def test_set_graph_headers() -> None:
    """Test that the method to set graph headers returns the expected dict."""
    config = AppConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_init_patches():
        connector = SharePointConnector(config=config)
        connector.set_graph_headers()

    assert connector.headers == {
        "Authorization": "Bearer fake-token",
        "Accept": "application/json",
    }


def test_ensure_destination_folder_success() -> None:
    """Test that ensure_destination_folder returns successfully when folder exists."""
    config = AppConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_init_patches():
        connector = SharePointConnector(config=config)

    with patch(
        "connector.sharepoint.requests.get",
        return_value=utils.build_response(
            status_code=200, json_body={"folder": {"name": "directory"}}
        ),
    ) as mock_get:
        connector.ensure_destination_folder(connector.drive_id, connector.headers)

    assert mock_get.call_count == 1
    assert mock_get.call_args[0][0] == (
        "https://graph.microsoft.com/v1.0/drives/fake-drive-id/root:/fake-folder-path"
    )
    assert mock_get.call_args[1]["headers"] == {
        "Accept": "application/json",
        "Authorization": "Bearer fake-token",
    }


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (
            utils.mock_ensure_destination_folder_response("folder", status_code=404),
            "Destination folder does not exist",
        ),
        (
            utils.mock_ensure_destination_folder_response("no_folder"),
            "Destination path exists but is not a folder",
        ),
    ],
)
def test_ensure_destination_folder_invalid_path(response: object, message: str) -> None:
    """Test that destination folder validation raises UploadError on bad paths."""
    config = AppConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_init_patches():
        connector = SharePointConnector(config=config)

    with (
        patch("connector.sharepoint.requests.get", return_value=response),
        pytest.raises(UploadError, match=message),
    ):
        connector.ensure_destination_folder(connector.drive_id, connector.headers)


def test_ensure_destination_folder_request_error() -> None:
    """Test that destination folder validation raises UploadError on request errors."""
    config = AppConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_init_patches():
        connector = SharePointConnector(config=config)

    with (
        patch(
            "connector.sharepoint.requests.get",
            side_effect=requests.RequestException("Mock request error"),
        ),
        pytest.raises(UploadError, match="Failed to verify destination folder"),
    ):
        connector.ensure_destination_folder(connector.drive_id, connector.headers)


# UP TO HERE


def test_get_site_id_success() -> None:
    """Test that get_site_id returns the SharePoint site id."""
    config = AppConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_init_patches():
        connector = SharePointConnector(config=config)

    with (
        patch(
            "connector.sharepoint.requests.post",
            return_value=utils.mock_token_response(),
        ) as mock_post,
        patch(
            "connector.sharepoint.requests.get",
            return_value=utils.mock_site_id_response(),
        ) as mock_get,
    ):
        site_id = connector.get_site_id()

    assert site_id == "fake-site-id"
    assert mock_post.call_count == 1
    assert mock_get.call_count == 1
    assert mock_get.call_args[0][0] == (
        "https://graph.microsoft.com/v1.0/sites/justiceuk.sharepoint.com:/sites/fake-site-name"
    )
    assert mock_get.call_args[1]["headers"] == {"Authorization": "Bearer fake-token"}


def test_create_upload_url_success() -> None:
    """Test that create_upload_url stores the returned upload URL."""
    config = AppConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_init_patches():
        connector = SharePointConnector(config=config)

    with patch(
        "connector.sharepoint.requests.post",
        return_value=utils.mock_upload_url_response(),
    ) as mock_post:
        connector.create_upload_url()

    assert connector.upload_url == "https://fake-upload-url"
    assert mock_post.call_count == 1


def test_create_download_url_success() -> None:
    """Test that create_download_url sets the expected content URL."""
    config = AppConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_init_patches():
        connector = SharePointConnector(config=config)

    connector.create_download_url()

    assert (
        connector.download_url
        == "https://graph.microsoft.com/v1.0/drives/fake-drive-id/root:/fake-folder-path/directory/fake-file.csv:/content"
    )


def test_fetch_file_success() -> None:
    """Test that fetch_file returns the response bytes."""
    config = AppConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_init_patches():
        connector = SharePointConnector(config=config)

    connector.create_download_url()

    with patch(
        "connector.sharepoint.requests.get",
        return_value=utils.mock_fetch_file_response(200),
    ):
        data = connector.fetch_file()

    assert data == b'{"content": "fake-file-content"}'


def test_fetch_file_not_found() -> None:
    """Test that fetch_file raises UploadError when the file is missing."""
    config = AppConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_init_patches():
        connector = SharePointConnector(config=config)

    connector.create_download_url()

    with (
        patch(
            "connector.sharepoint.requests.get",
            return_value=utils.build_response(status_code=404, json_body={}),
        ),
        pytest.raises(UploadError, match="File not found in SharePoint"),
    ):
        connector.fetch_file()


def test_verify_uploaded_file_success() -> None:
    """Test that verify_uploaded_file succeeds when the uploaded file is present."""
    config = AppConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_init_patches():
        connector = SharePointConnector(config=config)

    with patch(
        "connector.sharepoint.requests.get",
        return_value=utils.mock_verify_uploaded_file_response(200, config.FILE_KEY),
    ):
        connector.verify_uploaded_file()


def test_verify_uploaded_file_error() -> None:
    """Test that verify_uploaded_file raises UploadError when the file is absent."""
    config = AppConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_init_patches():
        connector = SharePointConnector(config=config)

    with (
        patch(
            "connector.sharepoint.requests.get",
            return_value=utils.build_response(
                status_code=200,
                json_body={"value": [{"name": "other-file", "file": {}}]},
            ),
        ),
        pytest.raises(UploadError, match="Verification failed"),
    ):
        connector.verify_uploaded_file()


def test_get_next_start_success() -> None:
    """Test that get_next_start parses the next expected range."""
    config = AppConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_init_patches():
        connector = SharePointConnector(config=config)

    connector.upload_url = "https://fake-upload-url"
    session = MagicMock()
    session.get.return_value = utils.mock_get_next_start_response(10, 20)

    start = connector.get_next_start(session=session)

    assert start == 10
    assert session.get.call_count == 1
    assert session.get.call_args[0][0] == "https://fake-upload-url"


def test_put_chunk_success() -> None:
    """Test that put_chunk sends the correct upload request data."""
    config = AppConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_init_patches():
        connector = SharePointConnector(config=config)

    connector.upload_url = "https://fake-upload-url"
    session = MagicMock()
    session.put.return_value = utils.mock_session_put_response()

    connector.put_chunk(
        start=0,
        data=b"Test content",
        file_size=12,
        session=session,
    )

    assert session.put.call_count == 1
    assert session.put.call_args[0][0] == "https://fake-upload-url"
    assert session.put.call_args[1]["headers"] == {
        "Content-Length": "12",
        "Content-Range": "bytes 0-11/12",
    }
    assert session.put.call_args[1]["data"] == b"Test content"


def test_upload_stream_in_chunks_success() -> None:
    """Test that upload_stream_in_chunks uploads data and verifies the result."""
    config = AppConfig()  # type: ignore[call-arg]

    with utils.sharepoint_connector_init_patches():
        connector = SharePointConnector(config=config)

    connector.upload_url = "https://fake-upload-url"
    session = MagicMock()
    session.get.return_value = utils.mock_get_next_start_response(0, 12)
    session.put.return_value = utils.mock_session_put_response()

    with (
        patch("connector.sharepoint.build_retry_session", return_value=session),
        patch.object(
            SharePointConnector,
            "verify_uploaded_file",
            autospec=True,
            return_value=None,
        ) as mock_verify,
    ):
        connector.upload_stream_in_chunks(BytesIO(b"Test content"), 12)

    assert session.get.call_count == 1
    assert session.put.call_count == 1
    assert session.put.call_args[0][0] == "https://fake-upload-url"
    assert session.put.call_args[1]["data"] == b"Test content"
    assert mock_verify.call_count == 1
    assert mock_verify.call_args[0][0] is connector
