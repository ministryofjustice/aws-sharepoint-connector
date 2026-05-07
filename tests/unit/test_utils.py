"""Unit tests for utility helpers in connector.utils."""

import json
from unittest.mock import patch

import pytest
import requests
from requests import Response

from connector import utils
from connector.constants import RETRYABLE_ERROR_CODES


def _sample_plan() -> dict[str, dict[str, str]]:
    return {
        "source": {"bucket": "my-bucket", "key": "path/file.csv"},
        "destination": {
            "site": "analytics-site",
            "library": "Documents",
            "filename": "file.csv",
        },
    }


def _response(status_code: int) -> Response:
    """Build a minimal Response object with the supplied status code."""
    response = Response()
    response.status_code = status_code
    return response


def test_parse_data_movement_plan_from_env_accepts_json_list() -> None:
    """It parses a JSON list payload and returns it unchanged."""
    plan = _sample_plan()
    raw = json.dumps([plan])

    parsed = utils.parse_data_movement_plan_from_env(raw)

    assert parsed == [plan]


def test_parse_data_movement_plan_from_env_wraps_json_dict() -> None:
    """It wraps a single decoded dict into a one-item list."""
    plan = _sample_plan()
    raw = json.dumps(plan)

    parsed = utils.parse_data_movement_plan_from_env(raw)

    assert parsed == [plan]


def test_parse_data_movement_plan_from_env_accepts_python_literal() -> None:
    """It supports Python-literal style input as a fallback path."""
    plan = _sample_plan()
    raw = str([plan])

    parsed = utils.parse_data_movement_plan_from_env(raw)

    assert parsed == [plan]


def test_parse_data_movement_plan_from_env_raises_for_unparsable_value() -> None:
    """It raises ValueError when input is neither valid JSON nor literal."""
    with pytest.raises(
        ValueError,
        match="Failed to parse DATA_MOVEMENT_PLAN as JSON or Python literal",
    ):
        utils.parse_data_movement_plan_from_env("not-a-valid-plan")


def test_parse_data_movement_plan_from_env_raises_for_wrong_decoded_type() -> None:
    """It raises ValueError when decoded payload is not dict/list[dict]."""
    with pytest.raises(
        ValueError,
        match="DATA_MOVEMENT_PLAN must decode to a dict or a list of dicts",
    ):
        utils.parse_data_movement_plan_from_env(json.dumps("plain-string"))


def test_request_with_retry_get_returns_on_first_success() -> None:
    """A successful GET returns immediately without sleeping."""
    with (
        patch("connector.utils.requests.get", return_value=_response(200)) as mock_get,
        patch("connector.utils.time.sleep") as mock_sleep,
    ):
        response = utils.request_with_retry("GET", "https://example.com")

    assert response.status_code == 200
    assert mock_get.call_count == 1
    mock_sleep.assert_not_called()


def test_request_with_retry_post_uses_post_request_function() -> None:
    """POST mode should dispatch through requests.post."""
    with patch(
        "connector.utils.requests.post", return_value=_response(201)
    ) as mock_post:
        response = utils.request_with_retry("POST", "https://example.com")

    assert response.status_code == 201
    assert mock_post.call_count == 1


def test_request_with_retry_retries_on_retryable_status_code() -> None:
    """Retryable HTTP status codes trigger a retry and backoff sleep."""
    retry_code = next(iter(RETRYABLE_ERROR_CODES))
    with (
        patch(
            "connector.utils.requests.get",
            side_effect=[_response(retry_code), _response(200)],
        ) as mock_get,
        patch("connector.utils.time.sleep") as mock_sleep,
    ):
        response = utils.request_with_retry(
            "GET", "https://example.com", max_attempts=3
        )

    assert response.status_code == 200
    assert mock_get.call_count == 2
    mock_sleep.assert_called_once_with(0.5)


def test_request_with_retry_returns_immediately_on_non_retryable_error_code() -> None:
    """Non-retryable status codes should be returned without retrying."""
    with (
        patch("connector.utils.requests.get", return_value=_response(400)) as mock_get,
        patch("connector.utils.time.sleep") as mock_sleep,
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
            "connector.utils.requests.get",
            side_effect=[requests.RequestException("boom"), _response(200)],
        ) as mock_get,
        patch("connector.utils.time.sleep") as mock_sleep,
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
            "connector.utils.requests.get",
            side_effect=requests.RequestException("still failing"),
        ) as mock_get,
        patch("connector.utils.time.sleep") as mock_sleep,
        pytest.raises(requests.RequestException, match="still failing"),
    ):
        utils.request_with_retry("GET", "https://example.com", max_attempts=3)

    assert mock_get.call_count == 3
    assert mock_sleep.call_count == 2


def test_request_with_retry_raises_for_unsupported_method() -> None:
    """Unsupported methods should fail fast with ValueError."""
    with pytest.raises(ValueError, match="Unsupported HTTP method"):
        utils.request_with_retry("PUT", "https://example.com")  # type: ignore[arg-type]
