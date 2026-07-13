"""Unit tests for utility helpers in connector.utils."""

from unittest.mock import call, patch

import pytest
import requests
from requests import Response

from aws_sharepoint_connector import exceptions, utils
from aws_sharepoint_connector.constants import RETRYABLE_ERROR_CODES


def _response(status_code: int) -> Response:
    """Build a minimal Response object with the supplied status code."""
    response = Response()
    response.status_code = status_code
    return response


def test_request_with_retry_get_returns_on_first_success() -> None:
    """A successful GET returns immediately without sleeping."""
    with (
        patch(
            "aws_sharepoint_connector.utils.requests.get", return_value=_response(200)
        ) as mock_get,
        patch("aws_sharepoint_connector.utils.time.sleep") as mock_sleep,
    ):
        response = utils.request_with_retry("GET", "https://example.com")

    assert response.status_code == 200
    assert mock_get.call_count == 1
    mock_sleep.assert_not_called()


def test_request_with_retry_post_uses_post_request_function() -> None:
    """POST mode should dispatch through requests.post."""
    with patch(
        "aws_sharepoint_connector.utils.requests.post", return_value=_response(201)
    ) as mock_post:
        response = utils.request_with_retry("POST", "https://example.com")

    assert response.status_code == 201
    assert mock_post.call_count == 1


def test_request_with_retry_delete_uses_delete_request_function() -> None:
    """DELETE mode should dispatch through requests.delete."""
    with patch(
        "aws_sharepoint_connector.utils.requests.delete", return_value=_response(204)
    ) as mock_delete:
        response = utils.request_with_retry("DELETE", "https://example.com")

    assert response.status_code == 204
    assert mock_delete.call_count == 1


def test_request_with_retry_retries_on_retryable_status_code() -> None:
    """Retryable HTTP status codes trigger a retry and backoff sleep."""
    retry_code = next(iter(RETRYABLE_ERROR_CODES))
    with (
        patch(
            "aws_sharepoint_connector.utils.requests.get",
            side_effect=[_response(retry_code), _response(200)],
        ) as mock_get,
        patch("aws_sharepoint_connector.utils.time.sleep") as mock_sleep,
    ):
        response = utils.request_with_retry(
            "GET", "https://example.com", max_attempts=3
        )

    assert response.status_code == 200
    assert mock_get.call_count == 2
    mock_sleep.assert_called_once_with(0.5)


def test_request_with_retry_uses_incremental_backoff_on_multiple_retries() -> None:
    """Backoff should increment per retry attempt for retryable status codes."""
    retry_code = next(iter(RETRYABLE_ERROR_CODES))
    with (
        patch(
            "aws_sharepoint_connector.utils.requests.get",
            side_effect=[
                _response(retry_code),
                _response(retry_code),
                _response(200),
            ],
        ) as mock_get,
        patch("aws_sharepoint_connector.utils.time.sleep") as mock_sleep,
    ):
        response = utils.request_with_retry(
            "GET", "https://example.com", max_attempts=3
        )

    assert response.status_code == 200
    assert mock_get.call_count == 3
    assert mock_sleep.call_args_list == [call(0.5), call(1.0)]


def test_request_with_retry_single_attempt_does_not_sleep() -> None:
    """No backoff should occur when only one attempt is allowed."""
    retry_code = next(iter(RETRYABLE_ERROR_CODES))
    with (
        patch(
            "aws_sharepoint_connector.utils.requests.get",
            return_value=_response(retry_code),
        ) as mock_get,
        patch("aws_sharepoint_connector.utils.time.sleep") as mock_sleep,
    ):
        response = utils.request_with_retry(
            "GET", "https://example.com", max_attempts=1
        )

    assert response.status_code == retry_code
    assert mock_get.call_count == 1
    mock_sleep.assert_not_called()


def test_request_with_retry_returns_immediately_on_non_retryable_error_code() -> None:
    """Non-retryable status codes should be returned without retrying."""
    with (
        patch(
            "aws_sharepoint_connector.utils.requests.get", return_value=_response(400)
        ) as mock_get,
        patch("aws_sharepoint_connector.utils.time.sleep") as mock_sleep,
    ):
        response = utils.request_with_retry(
            "GET", "https://example.com", max_attempts=3
        )

    assert response.status_code == 400
    assert mock_get.call_count == 1
    mock_sleep.assert_not_called()


def test_request_with_retry_retries_on_request_exception_then_succeeds() -> None:
    """Transient request exceptions retry and eventually return success."""
    with (
        patch(
            "aws_sharepoint_connector.utils.requests.get",
            side_effect=[requests.RequestException("boom"), _response(200)],
        ) as mock_get,
        patch("aws_sharepoint_connector.utils.time.sleep") as mock_sleep,
    ):
        response = utils.request_with_retry(
            "GET", "https://example.com", max_attempts=3
        )

    assert response.status_code == 200
    assert mock_get.call_count == 2
    mock_sleep.assert_called_once_with(0.5)


def test_request_with_retry_raises_after_max_attempts_on_request_exception() -> None:
    """When all attempts fail with request exceptions, the last one is raised."""
    with (
        patch(
            "aws_sharepoint_connector.utils.requests.get",
            side_effect=requests.RequestException("still failing"),
        ) as mock_get,
        patch("aws_sharepoint_connector.utils.time.sleep") as mock_sleep,
        pytest.raises(requests.RequestException, match="still failing"),
    ):
        utils.request_with_retry("GET", "https://example.com", max_attempts=3)

    assert mock_get.call_count == 3
    assert mock_sleep.call_count == 2


def test_request_with_retry_raises_for_unsupported_method() -> None:
    """Unsupported methods should fail fast with ValueError."""
    with pytest.raises(ValueError, match="Unsupported HTTP method"):
        utils.request_with_retry("PUT", "https://example.com")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("extensions", "expected"),
    [
        ("", ""),
        ("csv", "csv"),
        (".csv", "csv"),
        ("CSV", "csv"),
        (".XlSx", "xlsx"),
        ("  .Pdf  ", "pdf"),
        ("  ", ""),
        (".", ""),
    ],
)
def test_normalise_extension(extensions: str, expected: str) -> None:
    """normalise_extensions lowercases, strips dots, and drops empty values."""
    assert utils.normalise_extension(extensions) == expected


def test_validate_remote_path_accepts_relative_paths() -> None:
    """A normal relative path passes validation."""
    utils.validate_path("reports/2026/file.csv", "source")


def test_validate_remote_path_allows_empty_when_permitted() -> None:
    """An empty path is allowed only when allow_empty is set."""
    utils.validate_path("", "archive_folder", allow_empty=True)


@pytest.mark.parametrize(
    ("path", "expected_message"),
    [
        ("", "source must be a non-empty path"),
        ("/abs/path.csv", "source must be a relative path"),
        ("reports/../../etc/passwd", "source must not contain '..'"),
        ("reports\\2026\\file.csv", "source must use '/' as the path separator"),
        ("reports/2026/file\x01.csv", "source contains invalid control characters"),
    ],
)
def test_validate_remote_path_error_messages_include_field_name(
    path: str, expected_message: str
) -> None:
    """Validation errors should include field context and failure reason."""
    with pytest.raises(exceptions.InvalidPathError, match=expected_message):
        utils.validate_path(path, "source")


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/abs/path.csv",
        "../escape.csv",
        "reports/../../etc/passwd",
        "reports/2026/..",
        "reports\\2026\\file.csv",
        "reports/2026/file\x00.csv",
        "reports/2026/file\n.csv",
    ],
)
def test_validate_remote_path_rejects_unsafe_paths(path: str) -> None:
    """Empty, absolute, traversal, backslash, and control-char paths are rejected."""
    with pytest.raises(exceptions.InvalidPathError):
        utils.validate_path(path, "source")
