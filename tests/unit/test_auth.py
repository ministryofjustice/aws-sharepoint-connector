"""Unit tests for the auth module."""

from typing import Literal
from unittest.mock import patch

import pytest

from connector import auth
from connector.config import SecretConfig
from connector.exceptions import NoLibraryError
from tests import test_utils as utils


def test_get_azure_token() -> None:
    """Test that get_azure_token returns a token."""
    secrets = SecretConfig()  # type: ignore[call-arg]

    with patch(
        "azure.identity.ClientSecretCredential.get_token",
        side_effect=utils.mock_get_token,
    ):
        token = auth.get_azure_token(
            str(secrets.SECRET_AZURE_TENANT_ID),
            secrets.SECRET_AZURE_CLIENT_ID.get_secret_value(),
            secrets.SECRET_AZURE_CLIENT_SECRET.get_secret_value(),
        )
    assert token == "fake-token"  # noqa: S105  # nosec: B105 # nosec: B106


def test_get_drive_id_success() -> None:
    """Test that get_drive_id returns the correct drive ID."""
    _, plan = utils.create_s3_to_sp_movement_plan()
    site_id = plan.data_to_move[0].sp_site
    library_name = plan.data_to_move[0].sp_library
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
    _, plan = utils.create_s3_to_sp_movement_plan()
    site_id = plan.data_to_move[0].sp_site
    library_name = plan.data_to_move[0].sp_library
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
