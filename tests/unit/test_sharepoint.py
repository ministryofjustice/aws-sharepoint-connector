"""Unit tests for the sharepoint module."""

import logging
from io import BytesIO
from unittest.mock import MagicMock, Mock, patch

import pytest
import requests

from connector.config import SecretConfig
from connector.exceptions import UploadError
from connector.sharepoint import SharePointConnector
from tests import test_utils as utils


def test_sharepoint_connector_initialization() -> None:
    """Test that the SharePoint connector sets derived fields on init."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    with utils.sharepoint_connector_patches():
        connector = SharePointConnector(secrets=secrets, plan=plan.data_to_move[0])  # type: ignore[arg-type]

    assert connector.headers == {
        "Authorization": "Bearer fake-token",
        "Accept": "application/json",
    }
    assert connector.drive_id == "fake-drive-id"
    assert connector.file_path == "reports/2026/file1.csv"
    assert (
        connector.base_url
        == "https://graph.microsoft.com/v1.0/drives/fake-drive-id/root:/reports/2026/file1.csv:"
    )


def test_set_graph_headers() -> None:
    """Test that the method to set graph headers returns the expected dict."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    with utils.sharepoint_connector_patches():
        connector = SharePointConnector(secrets=secrets, plan=plan.data_to_move[0])  # type: ignore[arg-type]
        connector.set_graph_headers()

    assert connector.headers == {
        "Authorization": "Bearer fake-token",
        "Accept": "application/json",
    }


def test_ensure_destination_folder_success() -> None:
    """Test that ensure_destination_folder returns successfully when folder exists."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    with utils.sharepoint_connector_patches():
        connector = SharePointConnector(secrets=secrets, plan=plan.data_to_move[0])  # type: ignore[arg-type]

    with patch(
        "connector.sharepoint.requests.get",
        return_value=utils.build_response(
            status_code=200, json_body={"folder": {"name": "directory"}}
        ),
    ) as mock_get:
        connector.ensure_destination_folder(connector.drive_id, connector.headers)

    assert mock_get.call_count == 1
    assert mock_get.call_args[0][0] == (
        "https://graph.microsoft.com/v1.0/drives/fake-drive-id/root:/reports/2026"
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
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    with utils.sharepoint_connector_patches():
        connector = SharePointConnector(secrets=secrets, plan=plan.data_to_move[0])  # type: ignore[arg-type]

    with (
        patch("connector.sharepoint.requests.get", return_value=response),
        pytest.raises(UploadError, match=message),
    ):
        connector.ensure_destination_folder(connector.drive_id, connector.headers)


def test_ensure_destination_folder_request_error() -> None:
    """Test that destination folder validation raises UploadError on request errors."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    with utils.sharepoint_connector_patches():
        connector = SharePointConnector(secrets=secrets, plan=plan.data_to_move[0])  # type: ignore[arg-type]

    with (
        patch(
            "connector.sharepoint.requests.get",
            side_effect=requests.RequestException("Mock request error"),
        ),
        pytest.raises(UploadError, match="Failed to verify destination folder"),
    ):
        connector.ensure_destination_folder(connector.drive_id, connector.headers)


def test_get_site_id_success() -> None:
    """Test that get_site_id returns the SharePoint site id."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    with utils.sharepoint_connector_patches():
        connector = SharePointConnector(secrets=secrets, plan=plan.data_to_move[0])  # type: ignore[arg-type]

    with patch(
        "connector.sharepoint.requests.get",
        return_value=utils.mock_site_id_response(),
    ) as mock_get:
        site_id = connector.get_site_id()

    assert site_id == "fake-site-id"
    assert mock_get.call_count == 1
    assert mock_get.call_args[0][0] == (
        "https://graph.microsoft.com/v1.0/sites/justiceuk.sharepoint.com:/sites/analytics-site"
    )
    assert mock_get.call_args[1]["headers"] == {
        "Authorization": "Bearer fake-token",
        "Accept": "application/json",
    }


@pytest.mark.parametrize(
    ("exception"),
    [
        (requests.HTTPError("Mock HTTP error")),
        (ValueError("Mock value error")),
    ],
)
def test_set_drive_id_error(exception: Exception) -> None:
    """Test that set_drive_id raises UploadError when drive id retrieval fails."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    with (
        utils.sharepoint_connector_patches(),
        patch(
            "connector.sharepoint.SharePointConnector.get_site_id",
            side_effect=exception,
        ),
        pytest.raises(UploadError),
    ):
        SharePointConnector(secrets=secrets, plan=plan.data_to_move[0])  # type: ignore[arg-type].set_drive_id()


def test_set_base_url() -> None:
    """Test that set_base_url constructs the expected base URL."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    with utils.sharepoint_connector_patches():
        connector = SharePointConnector(secrets=secrets, plan=plan.data_to_move[0])  # type: ignore[arg-type]
        connector.set_base_url()

    assert (
        connector.base_url
        == "https://graph.microsoft.com/v1.0/drives/fake-drive-id/root:/reports/2026/file1.csv:"
    )


def test_set_upload_url() -> None:
    """Test that set_upload_url stores the returned upload URL."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    with utils.sharepoint_connector_patches():
        connector = SharePointConnector(secrets=secrets, plan=plan.data_to_move[0])  # type: ignore[arg-type]

    with patch(
        "connector.sharepoint.requests.post",
        return_value=utils.mock_upload_url_response(),
    ) as mock_post:
        connector.set_upload_url()

    assert connector.upload_url == "https://fake-upload-url"
    assert mock_post.call_count == 1
    assert mock_post.call_args[0][0] == (
        "https://graph.microsoft.com/v1.0/drives/fake-drive-id/root:/reports/2026/file1.csv:/createUploadSession"
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
    """Test that set_download_url sets the expected content URL."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    with utils.sharepoint_connector_patches():
        connector = SharePointConnector(secrets=secrets, plan=plan.data_to_move[0])  # type: ignore[arg-type]

    connector.set_download_url()

    assert (
        connector.download_url
        == "https://graph.microsoft.com/v1.0/drives/fake-drive-id/root:/reports/2026/file1.csv:/content"
    )


def test_fetch_file_success() -> None:
    """Test that fetch_file returns the response bytes."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    with utils.sharepoint_connector_patches():
        connector = SharePointConnector(secrets=secrets, plan=plan.data_to_move[0])  # type: ignore[arg-type]

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
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    with utils.sharepoint_connector_patches():
        connector = SharePointConnector(secrets=secrets, plan=plan.data_to_move[0])  # type: ignore[arg-type]

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
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    with utils.sharepoint_connector_patches():
        connector = SharePointConnector(secrets=secrets, plan=plan.data_to_move[0])  # type: ignore[arg-type]

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
    "folder_path",
    [
        (True),
        (False),
    ],
)
def test_verify_uploaded_file_success(
    folder_path: bool,  # noqa: FBT001
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that verify_uploaded_file succeeds when the uploaded file is present."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    file_plan = plan.data_to_move[5] if not folder_path else plan.data_to_move[0]  # type: ignore[union-attr]

    with utils.sharepoint_connector_patches():
        connector = SharePointConnector(secrets=secrets, plan=file_plan)  # type: ignore[arg-type]

    expected_size = 13

    with (
        patch(
            "connector.sharepoint.requests.get",
            return_value=utils.mock_verify_uploaded_file_response(
                200,
                file_plan.sp_file_name,
                expected_size,
            ),
        ) as mock_verify,
        caplog.at_level(logging.INFO, logger="s3-sharepoint"),
    ):
        connector.verify_uploaded_file(expected_size=expected_size)

    assert (
        f"Verified uploaded file '{file_plan.sp_file_name}' ({expected_size} bytes)"
        in caplog.text
    )
    assert mock_verify.call_count == 1

    expected_path = (
        "https://graph.microsoft.com/v1.0/drives/fake-drive-id/root:/reports/2026:/children?$select=name,size,file"
        if folder_path
        else "https://graph.microsoft.com/v1.0/drives/fake-drive-id/root/children?$select=name,size,file"
    )
    assert mock_verify.call_args[0][0] == expected_path
    assert mock_verify.call_args[1]["headers"] == {
        "Authorization": "Bearer fake-token",
        "Accept": "application/json",
    }


def test_verify_uploaded_not_found() -> None:
    """Test that verify_uploaded_file raises UploadError when the file is absent."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    with utils.sharepoint_connector_patches():
        connector = SharePointConnector(secrets=secrets, plan=plan.data_to_move[0])  # type: ignore[arg-type]

    with (
        patch(
            "connector.sharepoint.requests.get",
            return_value=utils.build_response(
                status_code=200,
                json_body={"value": [{"name": "other-file", "file": {}, "size": 10}]},
            ),
        ),
        pytest.raises(UploadError, match="Verification failed"),
    ):
        connector.verify_uploaded_file(expected_size=12)


def test_verify_uploaded_error() -> None:
    """Test that verify_uploaded_file raises UploadError when the file is absent."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    with utils.sharepoint_connector_patches():
        connector = SharePointConnector(secrets=secrets, plan=plan.data_to_move[0])  # type: ignore[arg-type]

    with (
        patch(
            "connector.sharepoint.requests.get",
            side_effect=requests.RequestException("Mock request error"),
        ),
        pytest.raises(UploadError, match="Failed to verify uploaded file"),
    ):
        connector.verify_uploaded_file(expected_size=12)


def test_get_next_start() -> None:
    """Test that get_next_start parses the next expected range."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    with utils.sharepoint_connector_patches():
        connector = SharePointConnector(secrets=secrets, plan=plan.data_to_move[0])  # type: ignore[arg-type]

    with patch(
        "connector.sharepoint.build_retry_session", return_value=MagicMock()
    ) as session:
        connector.upload_url = "https://fake-upload-url"
        session.get.return_value = utils.mock_get_next_start_response(10, 20)

        start = connector.get_next_start(session=session)

    assert start == 10
    assert session.get.call_count == 1
    assert session.get.call_args[0][0] == "https://fake-upload-url"


def test_put_chunk() -> None:
    """Test that put_chunk sends the correct upload request data."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    with utils.sharepoint_connector_patches():
        connector = SharePointConnector(secrets=secrets, plan=plan.data_to_move[0])  # type: ignore[arg-type]

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


@patch(
    "connector.sharepoint.SharePointConnector.verify_uploaded_file", return_value=None
)
def test_upload_stream_in_chunks_success(mock_verify: Mock) -> None:
    """Test that upload_stream_in_chunks uploads data and verifies the result."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    with utils.sharepoint_connector_patches():
        connector = SharePointConnector(secrets=secrets, plan=plan.data_to_move[0])  # type: ignore[arg-type]

    session = MagicMock()
    session.get.return_value = utils.mock_get_next_start_response(0, 11)
    session.put.side_effect = [
        utils.mock_session_put_response(),
        utils.mock_session_put_response(),
        utils.mock_session_put_response(),
    ]

    with (
        patch("connector.sharepoint.CHUNK_SIZE", 11),
        patch("connector.sharepoint.build_retry_session", return_value=session),
    ):
        connector.upload_url = "https://fake-upload-url"
        connector.upload_stream_in_chunks(
            BytesIO(b"This11bytesThat11bytesAlso11bytes"), 33
        )

    assert session.get.call_count == 1
    assert session.put.call_count == 3
    assert session.put.call_args_list[0][0][0] == "https://fake-upload-url"
    assert session.put.call_args_list[0][1]["data"] == b"This11bytes"
    assert session.put.call_args_list[1][1]["data"] == b"That11bytes"
    assert session.put.call_args_list[2][1]["data"] == b"Also11bytes"
    mock_verify.assert_called_once_with(expected_size=33)


@patch(
    "connector.sharepoint.SharePointConnector.verify_uploaded_file", return_value=None
)
def test_upload_stream_in_chunks_request_exception_logs_and_recovers(
    mock_verify: Mock, caplog: pytest.LogCaptureFixture
) -> None:
    """Test chunk upload logs warning/info and resumes after RequestException."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    with utils.sharepoint_connector_patches():
        connector = SharePointConnector(secrets=secrets, plan=plan.data_to_move[0])  # type: ignore[arg-type]
        connector.upload_url = "https://fake-upload-url"

    session = MagicMock()
    session.get.side_effect = [
        utils.mock_get_next_start_response(0, 11),
        utils.mock_get_next_start_response(11, 22),
    ]
    session.put.side_effect = [
        requests.RequestException("Mock chunk upload error"),
        utils.mock_session_put_response(),
        utils.mock_session_put_response(),
    ]

    with (
        caplog.at_level(logging.INFO, logger="s3-sharepoint"),
        patch("connector.sharepoint.CHUNK_SIZE", 11),
        patch("connector.sharepoint.build_retry_session", return_value=session),
    ):
        connector.upload_stream_in_chunks(
            BytesIO(b"This11bytesThat11bytesAlso11bytes"), 33
        )

    assert session.get.call_count == 2
    assert session.put.call_count == 3
    assert session.put.call_args_list[0][1]["data"] == b"This11bytes"
    assert session.put.call_args_list[1][1]["data"] == b"That11bytes"
    assert session.put.call_args_list[2][1]["data"] == b"Also11bytes"
    assert "Chunk upload failed, attempting to resume..." in caplog.text
    assert "Resuming from 11 after partial upload" in caplog.text
    mock_verify.assert_called_once_with(expected_size=33)


@patch(
    "connector.sharepoint.SharePointConnector.verify_uploaded_file", return_value=None
)
def test_upload_stream_in_chunks_bad_request(mock_verify: Mock) -> None:
    """Test that bad status responses call raise_for_status and trigger resume."""
    secrets = SecretConfig()  # type: ignore[call-arg]
    _, plan = utils.create_sp_to_s3_movement_plan()  # type: ignore[assignment]

    with utils.sharepoint_connector_patches():
        connector = SharePointConnector(secrets=secrets, plan=plan.data_to_move[0])  # type: ignore[arg-type]
        connector.upload_url = "https://fake-upload-url"

    bad_response = MagicMock()
    bad_response.status_code = 400
    bad_response.raise_for_status.side_effect = requests.HTTPError("Mock HTTP error")

    session = MagicMock()
    session.get.side_effect = [
        utils.mock_get_next_start_response(0, 11),
        utils.mock_get_next_start_response(11, 22),
    ]
    session.put.side_effect = [
        bad_response,
        utils.mock_session_put_response(),
        utils.mock_session_put_response(),
    ]

    with (
        patch("connector.sharepoint.CHUNK_SIZE", 11),
        patch("connector.sharepoint.build_retry_session", return_value=session),
    ):
        connector.upload_stream_in_chunks(
            BytesIO(b"This11bytesThat11bytesAlso11bytes"), 33
        )

    bad_response.raise_for_status.assert_called_once_with()
    assert session.get.call_count == 2
    assert session.put.call_count == 3
    mock_verify.assert_called_once_with(expected_size=33)
