"""Unit tests for the auth module."""

from typing import Literal
from unittest.mock import patch

import pytest

from connector import auth
from connector.config import AppConfig
from connector.exceptions import NoLibraryError
from tests import test_utils as utils


def test_get_azure_token() -> None:
    """Test that get_azure_token returns a token."""
    config = AppConfig()  # type: ignore[call-arg]

    with patch(
        "azure.identity.ClientSecretCredential.get_token",
        side_effect=utils.mock_get_token,
    ):
        token = auth.get_azure_token(
            str(config.SECRET_AZURE_TENANT_ID),
            config.SECRET_AZURE_CLIENT_ID.get_secret_value(),
            config.SECRET_AZURE_CLIENT_SECRET.get_secret_value(),
        )
    assert token == "fake-token"  # noqa: S105  noqa: B106


def test_get_drive_id_success() -> None:
    """Test that get_drive_id returns the correct drive ID."""
    config = AppConfig()  # type: ignore[call-arg]
    site_id = config.SP_SITE_NAME
    library_name = config.SP_LIBRARY_NAME
    headers = {"Authorization": "Bearer fake-token"}

    with patch(
        "requests.get", return_value=utils.mock_drive_id_response("complete")
    ) as mock_get:
        drive_id = auth.get_drive_id(site_id, library_name, headers)

    assert drive_id == "fake-drive-id"
    assert mock_get.call_count == 1
    assert (
        mock_get.call_args[0][0]
        == f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
    )
    assert mock_get.call_args[1]["headers"] == headers
    assert mock_get.call_args[1]["timeout"] == 30


@pytest.mark.parametrize(
    "content",
    ["no_drives", "no_value"],
)
def test_get_drive_id_empty(content: Literal["no_drives", "no_value"]) -> None:
    """Test that get_drive_id raises a ValueError when the response is empty."""
    config = AppConfig()  # type: ignore[call-arg]
    site_id = config.SP_SITE_NAME
    library_name = config.SP_LIBRARY_NAME
    headers = {"Authorization": "Bearer fake-token"}

    with (
        patch(
            "requests.get", return_value=utils.mock_drive_id_response(content)
        ) as mock_get,
        pytest.raises(NoLibraryError),
    ):
        auth.get_drive_id(site_id, library_name, headers)
    assert mock_get.call_count == 1
    assert (
        mock_get.call_args[0][0]
        == f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
    )
    assert mock_get.call_args[1]["headers"] == headers
    assert mock_get.call_args[1]["timeout"] == 30
