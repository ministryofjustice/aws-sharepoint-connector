"""Unit tests for the sharepoint module."""

import logging
from io import BytesIO
from typing import Literal
from unittest.mock import patch

import pytest
import requests

from connector.config import SecretConfig
from connector.exceptions import (
    FileSizeMismatchError,
    IncorrectObjectTypeError,
    NoLibraryError,
    NoSiteError,
    ObjectNotFoundError,
    ProcessingError,
)
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


def make_connector() -> SharePointConnector:
    """Create a SharePointConnector with patched HTTP calls."""
    with utils.sharepoint_connector_patches():
        return SharePointConnector(
            secrets=SecretConfig(),  # type: ignore[call-arg]
            library=utils.make_sharepoint_library(),
        )


def test_sharepoint_connector_initialization() -> None:
    """Test that SharePointConnector sets up headers and drive_id on init."""
    connector = make_connector()

    assert connector.headers == {
        "Authorization": "Bearer fake-token",
        "Accept": "application/json",
    }
    assert connector.drive_id == "fake-drive-id"
    assert connector.file_path == ""
    assert connector.base_url == ""


def test_set_graph_headers() -> None:
    """Test that set_graph_headers populates the correct auth headers."""
    connector = make_connector()
    with utils.sharepoint_connector_patches():
        connector.set_graph_headers()

    assert connector.headers == {
        "Authorization": "Bearer fake-token",
        "Accept": "application/json",
    }


def test_get_site_id_success() -> None:
    """Test that get_site_id returns the site id and calls the correct URL."""
    connector = make_connector()

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


def test_get_site_id_missing_id() -> None:
    """Test that get_site_id raises NoSiteError when Graph omits 'id'."""
    connector = make_connector()

    with (
        patch(
            "connector.sharepoint.requests.get",
            return_value=utils.build_response(status_code=200, json_body={}),
        ),
        pytest.raises(NoSiteError, match="no site ID"),
    ):
        connector.get_site_id()


def test_get_drive_id_success() -> None:
    """Test that get_drive_id returns the drive id and calls the correct URL."""
    connector = make_connector()

    with patch(
        "connector.sharepoint.requests.get",
        side_effect=[
            utils.mock_site_id_response(),
            utils.mock_drive_id_response(content="complete"),
        ],
    ) as mock_get:
        connector.set_drive_id()

    assert connector.drive_id == "fake-drive-id"
    assert mock_get.call_count == 2
    assert mock_get.call_args_list[0].args[0] == (
        "https://graph.microsoft.com/v1.0/sites/"
        "justiceuk.sharepoint.com:/sites/analytics-site"
    )
    assert mock_get.call_args_list[0].kwargs["headers"] == {
        "Authorization": "Bearer fake-token",
        "Accept": "application/json",
    }
    assert mock_get.call_args_list[1].args[0] == (
        "https://graph.microsoft.com/v1.0/sites/fake-site-id/drives"
    )
    assert mock_get.call_args_list[1].kwargs["headers"] == {
        "Authorization": "Bearer fake-token",
        "Accept": "application/json",
    }


@pytest.mark.parametrize(
    "exception",
    [
        requests.HTTPError("Mock HTTP error"),
        ValueError("Mock value error"),
    ],
)
def test_set_drive_id_error(exception: Exception) -> None:
    """Test that set_drive_id raises ProcessingError when drive retrieval fails."""
    with (
        utils.sharepoint_connector_patches(),
        patch(
            "connector.sharepoint.SharePointConnector.get_site_id",
            side_effect=exception,
        ),
        pytest.raises(ProcessingError),
    ):
        make_connector()


def test_set_drive_id_no_library_error() -> None:
    """Test that set_drive_id wraps NoLibraryError from auth.get_drive_id."""
    with (
        utils.sharepoint_connector_patches(),
        patch(
            "connector.auth.get_drive_id",
            side_effect=NoLibraryError("Library 'Documents' not found on site 'x'"),
        ),
        pytest.raises(ProcessingError, match="Could not connect to SharePoint library"),
    ):
        make_connector()


def test_set_base_url() -> None:
    """Test that set_base_url constructs the expected Graph API base URL."""
    connector = make_connector()

    connector.update_with_file_path(SP_FILE_PATH)
    connector.set_base_url()

    assert connector.base_url == EXPECTED_BASE_URL


def test_update_with_file_path() -> None:
    """Test that update_with_file_path stores path and derives base_url."""
    connector = make_connector()

    connector.update_with_file_path(SP_FILE_PATH)

    assert connector.file_path == SP_FILE_PATH
    assert connector.base_url == EXPECTED_BASE_URL


def test_set_upload_url() -> None:
    """Test that set_upload_url stores the correct upload URL."""
    connector = make_connector()

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
    connector = make_connector()

    connector.update_with_file_path(SP_FILE_PATH)
    connector.set_download_url()

    assert connector.download_url == (
        "https://graph.microsoft.com/v1.0/drives/fake-drive-id"
        "/root:/reports/2026/file1.csv:/content"
    )


def test_set_archive_url() -> None:
    """Test that set_archive_url builds the correct archive URL."""
    connector = make_connector()

    connector.update_with_file_path(SP_FILE_PATH)
    connector.set_archive_url("archive/reports/2026/")

    assert connector.archive_url == (
        "https://graph.microsoft.com/v1.0/drives/fake-drive-id"
        "/root:/archive/reports/2026/file1.csv:/content"
    )


def test_list_files_success() -> None:
    """list_files returns file names from the library root, excluding folders."""
    connector = make_connector()
    root_page = utils.mock_list_files_response(
        file_names=["report.csv", "summary.xlsx"],
        folder_names=["archive"],
    )
    archive_page = utils.mock_list_files_response(file_names=[])

    with patch(
        "connector.sharepoint.requests.get",
        side_effect=[root_page, archive_page],
    ):
        result = connector.list_files()
    assert result == ["report.csv", "summary.xlsx"]


def test_list_files_pagination() -> None:
    """list_files follows @odata.nextLink to return all pages of results."""
    page1 = utils.mock_list_files_response(
        file_names=["a.csv"], next_link="https://graph.microsoft.com/v1.0/nextpage"
    )
    page2 = utils.mock_list_files_response(file_names=["b.csv", "c.csv"])
    connector = make_connector()
    with patch(
        "connector.sharepoint.requests.get",
        side_effect=[page1, page2],
    ):
        result = connector.list_files()
    assert result == ["a.csv", "b.csv", "c.csv"]


def test_list_files_recurses_into_folders() -> None:
    """list_files includes files found in nested folders."""
    root_page = utils.mock_list_files_response(
        file_names=[],
        folder_names=["scenario_1"],
    )
    child_page = utils.mock_list_files_response(
        file_names=["a.csv", "b.csv"],
    )

    connector = make_connector()
    with patch(
        "connector.sharepoint.requests.get",
        side_effect=[root_page, child_page],
    ):
        result = connector.list_files()

    assert result == ["scenario_1/a.csv", "scenario_1/b.csv"]


def test_list_files_request_error() -> None:
    """list_files raises ProcessingError when the listing request fails."""
    connector = make_connector()
    with (
        patch(
            "connector.sharepoint.requests.get",
            side_effect=requests.RequestException("timeout"),
        ),
        pytest.raises(
            ProcessingError, match="Failed to list files in SharePoint library"
        ),
    ):
        connector.list_files()


@pytest.mark.parametrize(
    ("object_type", "object_name"),
    [
        ("file", SP_FILE_NAME),
        ("folder", "2026"),
    ],
)
def test_check_object_exists_success(
    object_type: Literal["file", "folder"], object_name: str
) -> None:
    """check_object_exists does not raise when the object is present."""
    connector = make_connector()
    response = utils.mock_check_object_response(200, object_name, object_type)
    with patch(
        "connector.sharepoint.requests.get",
        return_value=response,
    ):
        connector.check_object_exists(
            f"reports/{object_name}", object_type
        )  # should not raise


@pytest.mark.parametrize(
    ("object_type", "object_name", "match_message"),
    [
        ("file", SP_FILE_NAME, "File not found in SharePoint"),
        ("folder", "2026", "Folder not found in SharePoint"),
    ],
)
def test_check_object_exists_not_found(
    object_type: Literal["file", "folder"], object_name: str, match_message: str
) -> None:
    """check_object_exists raises ObjectNotFoundError when the file is absent."""
    connector = make_connector()
    with (
        patch(
            "connector.sharepoint.requests.get",
            return_value=utils.build_response(status_code=404, json_body={}),
        ),
        pytest.raises(ObjectNotFoundError, match=match_message),
    ):
        connector.check_object_exists(object_name, object_type)


@pytest.mark.parametrize(
    ("object_type", "json_body", "input_path"),
    [
        (
            "file",
            {"name": "reports"},
            "reports",
        ),
        (
            "folder",
            {"name": "daily_report.csv"},
            "daily_report.csv",
        ),
    ],
)
def test_check_object_exists_incorrect_type(
    object_type: Literal["file", "folder"],
    json_body: dict[str, str],
    input_path: str,
) -> None:
    """check_object_exists raises IncorrectObjectTypeError if path is wrong type."""
    folder_as_file_response = utils.build_response(
        status_code=200,
        json_body=json_body,
    )
    with utils.sharepoint_connector_patches(
        extra_get_side_effects=[folder_as_file_response],
    ):
        connector = make_connector()
        with pytest.raises(
            IncorrectObjectTypeError,
            match=f"SharePoint path 'reports/{input_path}' exists but is not a"
            f" {object_type}",
        ):
            connector.check_object_exists(f"reports/{input_path}", object_type)


@pytest.mark.parametrize(
    "object_type",
    ["file", "folder"],
)
def test_check_object_exists_request_error(
    object_type: Literal["file", "folder"],
) -> None:
    """check_object_exists raises ProcessingError on a network error for file check."""
    connector = make_connector()
    with (
        patch(
            "connector.sharepoint.requests.get",
            side_effect=requests.RequestException("network error"),
        ),
        pytest.raises(
            ProcessingError, match=f"Failed to check SharePoint {object_type} existence"
        ),
    ):
        connector.check_object_exists(SP_FILE_PATH, object_type)


def test_fetch_file_success() -> None:
    """Test that fetch_file returns the response bytes."""
    connector = make_connector()

    connector.update_with_file_path(SP_FILE_PATH)
    connector.set_download_url()

    with patch(
        "connector.sharepoint.requests.get",
        return_value=utils.mock_fetch_file_response(200),
    ):
        data = connector.fetch_file()

    assert data == b"fake-file-content"


def test_fetch_file_not_found() -> None:
    """Test that fetch_file raises ObjectNotFoundError when the file is missing."""
    connector = make_connector()

    connector.update_with_file_path(SP_FILE_PATH)
    connector.set_download_url()

    with (
        patch(
            "connector.sharepoint.requests.get",
            return_value=utils.mock_fetch_file_response(404),
        ),
        pytest.raises(ObjectNotFoundError, match="File not found in SharePoint"),
    ):
        connector.fetch_file()


def test_fetch_file_request_error() -> None:
    """Test that fetch_file raises ProcessingError on request errors."""
    connector = make_connector()

    connector.update_with_file_path(SP_FILE_PATH)
    connector.set_download_url()

    with (
        patch(
            "connector.sharepoint.requests.get",
            side_effect=requests.RequestException("Mock request error"),
        ),
        pytest.raises(ProcessingError, match="Failed to fetch file from SharePoint"),
    ):
        connector.fetch_file()


@pytest.mark.parametrize(
    ("verify_type", "file_path", "expected_verify_url"),
    [
        (
            "destination",
            SP_FILE_PATH,
            "https://graph.microsoft.com/v1.0/drives/fake-drive-id"
            "/root:/reports/2026/file1.csv:?$select=name,size,file",
        ),
        (
            "destination",
            SP_FILE_PATH_NO_DIR,
            "https://graph.microsoft.com/v1.0/drives/fake-drive-id"
            "/root:/file6.csv:?$select=name,size,file",
        ),
        (
            "archive",
            SP_FILE_PATH,
            "https://graph.microsoft.com/v1.0/drives/fake-drive-id"
            "/root:/archive/reports/2026/file1.csv:?$select=name,size,file",
        ),
    ],
)
def test_verify_uploaded_file_success(
    verify_type: Literal["destination", "archive"],
    file_path: str,
    expected_verify_url: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that verify_uploaded_file succeeds when the uploaded file is present."""
    expected_size = 13
    file_name = file_path.rsplit("/", maxsplit=1)[-1]

    connector = make_connector()
    connector.update_with_file_path(file_path)
    connector.set_archive_url("archive/reports/2026/")  # for archive verification

    with (
        patch(
            "connector.sharepoint.requests.get",
            return_value=utils.mock_verify_uploaded_file_response(
                200, file_name, expected_size
            ),
        ) as mock_verify,
        caplog.at_level(logging.INFO, logger="s3-sharepoint"),
    ):
        connector.verify_uploaded_file(expected_size, verify_type=verify_type)

    assert (
        f"Verified SharePoint upload for '{file_name}' ({expected_size} bytes)."
        in caplog.text
    )
    assert mock_verify.call_count == 1
    assert mock_verify.call_args[0][0] == expected_verify_url
    assert mock_verify.call_args[1]["headers"] == {
        "Authorization": "Bearer fake-token",
        "Accept": "application/json",
    }


def test_verify_uploaded_not_found() -> None:
    """Test that verify_uploaded_file raises ObjectNotFoundError when file is absent."""
    connector = make_connector()

    connector.update_with_file_path(SP_FILE_PATH)

    with (
        patch(
            "connector.sharepoint.requests.get",
            return_value=utils.build_response(status_code=404),
        ),
        pytest.raises(ObjectNotFoundError, match="Verification failed"),
    ):
        connector.verify_uploaded_file(expected_size=12, verify_type="destination")


def test_verify_uploaded_size_mismatch() -> None:
    """Test verify_uploaded_file raises FileSizeMismatchError if size does not match."""
    connector = make_connector()

    connector.update_with_file_path(SP_FILE_PATH)

    with (
        patch(
            "connector.sharepoint.requests.get",
            return_value=utils.build_response(
                status_code=200,
                json_body={"name": SP_FILE_NAME, "size": 999, "file": {}},
            ),
        ),
        pytest.raises(FileSizeMismatchError, match="Verification failed"),
    ):
        connector.verify_uploaded_file(expected_size=12, verify_type="destination")


def test_verify_uploaded_file_request_error() -> None:
    """Test that verify_uploaded_file raises ProcessingError on RequestException."""
    connector = make_connector()

    connector.update_with_file_path(SP_FILE_PATH)

    with (
        patch(
            "connector.sharepoint.requests.get",
            side_effect=requests.RequestException("network error"),
        ),
        pytest.raises(ProcessingError, match="Failed to verify uploaded file"),
    ):
        connector.verify_uploaded_file(expected_size=12, verify_type="destination")


def test_upload_stream_in_chunks_success() -> None:
    """Test that a small payload is uploaded in a single chunk."""
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
        connector = make_connector()
        connector.update_with_file_path(SP_FILE_PATH)
        connector.set_upload_url()
        connector.upload_stream_in_chunks(BytesIO(payload), len(payload))

    assert mock_put.call_count == 1
    assert mock_put.call_args[1]["data"] == payload


def test_upload_stream_in_chunks_permanent_error_raises() -> None:
    """Test that a 400-range (non-429) response aborts the upload."""
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
        connector = make_connector()
        connector.update_with_file_path(SP_FILE_PATH)
        connector.set_upload_url()
        with pytest.raises(ProcessingError, match="permanent HTTP 403"):
            connector.upload_stream_in_chunks(BytesIO(payload), len(payload))


def test_upload_stream_in_chunks_exceeds_retries_raises() -> None:
    """Test that exceeding MAX_CHUNK_RETRIES raises ProcessingError."""
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
        connector = make_connector()
        connector.update_with_file_path(SP_FILE_PATH)
        connector.set_upload_url()
        with pytest.raises(ProcessingError, match="retries"):
            connector.upload_stream_in_chunks(BytesIO(payload), len(payload))


def test_upload_stream_in_chunks_request_exception_resumes_from_new_position() -> None:
    """Test chunk upload resumes from server-reported position after Exception."""
    payload = b"0123456789abcdef"  # 16 bytes
    file_size = len(payload)
    resume_pos = 5

    with (
        utils.sharepoint_connector_patches(
            extra_post_side_effects=[utils.mock_upload_url_response()],
            extra_get_side_effects=[
                utils.mock_verify_uploaded_file_response(200, SP_FILE_NAME, file_size),
            ],
        ),
        patch(
            "connector.sharepoint.requests.Session.get",
            side_effect=[
                utils.mock_get_next_start_response(0, file_size),
                utils.mock_get_next_start_response(resume_pos, file_size),
            ],
        ),
        patch(
            "connector.sharepoint.requests.Session.put",
            side_effect=[
                requests.exceptions.RequestException("network error"),
                utils.mock_session_put_response(200),
            ],
        ) as mock_put,
    ):
        connector = make_connector()
        connector.update_with_file_path(SP_FILE_PATH)
        connector.set_upload_url()
        connector.upload_stream_in_chunks(BytesIO(payload), file_size)

    assert mock_put.call_count == 2
    # Second put starts from resume_pos, so only the remaining bytes are sent
    assert len(mock_put.call_args_list[1][1]["data"]) == file_size - resume_pos


def test_upload_stream_in_chunks_transient_error_exceeds_retries_raises() -> None:
    """Test that a 5xx response exceeding MAX_CHUNK_RETRIES raises ProcessingError."""
    payload = b"chunk-content"
    file_size = len(payload)
    # MAX_CHUNK_RETRIES=5: 6 puts all fail; 6 Session.get calls (1 initial + 5 resumes)
    session_get_responses = [utils.mock_get_next_start_response(0, file_size)] * 6
    session_put_responses = [utils.mock_session_put_response(503)] * 6

    with (
        utils.sharepoint_connector_patches(
            extra_post_side_effects=[utils.mock_upload_url_response()],
        ),
        patch(
            "connector.sharepoint.requests.Session.get",
            side_effect=session_get_responses,
        ),
        patch(
            "connector.sharepoint.requests.Session.put",
            side_effect=session_put_responses,
        ),
    ):
        connector = make_connector()
        connector.update_with_file_path(SP_FILE_PATH)
        connector.set_upload_url()
        with pytest.raises(ProcessingError, match="retries"):
            connector.upload_stream_in_chunks(BytesIO(payload), file_size)


def test_upload_stream_in_chunks_transient_error_resumes_from_new_position() -> None:
    """Test chunk upload resumes from server-reported position after a 5xx response."""
    payload = b"0123456789abcdef"  # 16 bytes
    file_size = len(payload)
    resume_pos = 5

    with (
        utils.sharepoint_connector_patches(
            extra_post_side_effects=[utils.mock_upload_url_response()],
            extra_get_side_effects=[
                utils.mock_verify_uploaded_file_response(200, SP_FILE_NAME, file_size),
            ],
        ),
        patch(
            "connector.sharepoint.requests.Session.get",
            side_effect=[
                utils.mock_get_next_start_response(0, file_size),
                utils.mock_get_next_start_response(resume_pos, file_size),
            ],
        ),
        patch(
            "connector.sharepoint.requests.Session.put",
            side_effect=[
                utils.mock_session_put_response(503),
                utils.mock_session_put_response(200),
            ],
        ) as mock_put,
    ):
        connector = make_connector()
        connector.update_with_file_path(SP_FILE_PATH)
        connector.set_upload_url()
        connector.upload_stream_in_chunks(BytesIO(payload), file_size)

    assert mock_put.call_count == 2
    assert len(mock_put.call_args_list[1][1]["data"]) == file_size - resume_pos


def test_archive_file_success() -> None:
    """archive_file uploads a copy, verifies it, then deletes the source file."""
    payload = b"archived-content"
    connector = make_connector()
    connector.update_with_file_path(SP_FILE_PATH)
    connector.set_archive_url("archive/reports/2026/")

    with (
        patch.object(
            SharePointConnector,
            "fetch_file",
            return_value=payload,
        ) as mock_fetch,
        patch(
            "connector.sharepoint.requests.put",
            return_value=utils.build_response(status_code=201),
        ) as mock_put,
        patch.object(SharePointConnector, "verify_uploaded_file") as mock_verify,
        patch.object(SharePointConnector, "delete_file") as mock_delete,
    ):
        connector.archive_file(content_size=len(payload))

    mock_fetch.assert_called_once_with()
    assert mock_put.call_count == 1
    assert mock_put.call_args[0][0] == connector.archive_url
    assert mock_put.call_args[1]["data"] == payload
    mock_verify.assert_called_once_with(
        expected_size=len(payload), verify_type="archive"
    )
    mock_delete.assert_called_once_with()


def test_archive_file_request_error() -> None:
    """archive_file does not delete source when archive upload request fails."""
    connector = make_connector()
    connector.update_with_file_path(SP_FILE_PATH)
    connector.set_archive_url("archive/reports/2026/")

    with (
        patch.object(
            SharePointConnector,
            "fetch_file",
            return_value=b"content",
        ),
        patch(
            "connector.sharepoint.requests.put",
            side_effect=requests.RequestException("network error"),
        ),
        patch.object(SharePointConnector, "delete_file") as mock_delete,
        pytest.raises(ProcessingError, match="Failed to archive file in SharePoint"),
    ):
        connector.archive_file(content_size=7)

    mock_delete.assert_not_called()


def test_delete_file_success() -> None:
    """delete_file sends a DELETE request to the expected SharePoint URL."""
    connector = make_connector()
    connector.update_with_file_path(SP_FILE_PATH)
    expected_url = (
        "https://graph.microsoft.com/v1.0/drives/fake-drive-id"
        "/root:/reports/2026/file1.csv:?$select=name,file"
    )

    with patch(
        "connector.sharepoint.requests.delete",
        return_value=utils.build_response(status_code=204),
    ) as mock_delete:
        connector.delete_file()

    assert mock_delete.call_count == 1
    assert mock_delete.call_args[0][0] == expected_url
    assert mock_delete.call_args[1]["headers"] == {
        "Authorization": "Bearer fake-token",
        "Accept": "application/json",
    }


def test_delete_file_not_found() -> None:
    """delete_file raises ObjectNotFoundError when SharePoint returns 404."""
    connector = make_connector()
    connector.update_with_file_path(SP_FILE_PATH)

    with (
        patch(
            "connector.sharepoint.requests.delete",
            return_value=utils.build_response(status_code=404),
        ),
        pytest.raises(
            ObjectNotFoundError, match="File not found in SharePoint for deletion"
        ),
    ):
        connector.delete_file()


def test_delete_file_request_error() -> None:
    """delete_file raises ProcessingError when the DELETE request fails."""
    connector = make_connector()
    connector.update_with_file_path(SP_FILE_PATH)

    with (
        patch(
            "connector.sharepoint.requests.delete",
            side_effect=requests.RequestException("network error"),
        ),
        pytest.raises(ProcessingError, match="Failed to delete file from SharePoint"),
    ):
        connector.delete_file()
