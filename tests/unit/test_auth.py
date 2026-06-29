"""Unit tests for the auth module."""

from typing import Literal
from unittest.mock import patch

import pytest
from azure.core.exceptions import ClientAuthenticationError
from azure.identity import CredentialUnavailableError

from aws_sharepoint_connector import auth
from aws_sharepoint_connector.config import SecretConfig
from aws_sharepoint_connector.exceptions import NoLibraryError
from tests import test_utils as utils

SP_SITE_ID = utils.SP_SITE  # used as fake site_id value in drive tests
SP_LIBRARY = utils.SP_LIBRARY  # "Documents"


def test_get_azure_token() -> None:
    """Test that get_azure_token returns the expected token string."""
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
    assert token == "fake-token"  # noqa: S105  # nosec: B105


@pytest.mark.parametrize(
    "exception",
    [
        CredentialUnavailableError("credential unavailable"),
        ClientAuthenticationError("authentication failed"),
    ],
)
def test_get_azure_token_error(exception: Exception) -> None:
    """get_azure_token raises ProcessingError when Azure auth fails."""
    secrets = SecretConfig()  # type: ignore[call-arg]

    with (
        patch(
            "azure.identity.ClientSecretCredential.get_token",
            side_effect=exception,
        ),
        pytest.raises(
            ProcessingError,
            match="Failed to obtain Azure token",
        ),
    ):
        auth.get_azure_token(
            str(secrets.SECRET_AZURE_TENANT_ID),
            secrets.SECRET_AZURE_CLIENT_ID.get_secret_value(),
            secrets.SECRET_AZURE_CLIENT_SECRET.get_secret_value(),
        )


def test_get_drive_id_success() -> None:
    """Test that get_drive_id returns the correct drive ID."""
    headers = {"Authorization": "Bearer fake-token"}

    with patch(
        "requests.get", return_value=utils.mock_drive_id_response("complete")
    ) as mock_get:
        drive_id = auth.get_drive_id(SP_SITE_ID, SP_LIBRARY, headers)

    assert drive_id == "fake-drive-id"
    assert mock_get.call_count == 1
    assert (
        mock_get.call_args[0][0]
        == f"https://graph.microsoft.com/v1.0/sites/{SP_SITE_ID}/drives"
    )
    assert mock_get.call_args[1]["headers"] == headers
    assert mock_get.call_args[1]["timeout"] == 30


@pytest.mark.parametrize(
    "content",
    ["no_drives", "no_value"],
)
def test_get_drive_id_library_not_found_raises(
    content: Literal["no_drives", "no_value"],
) -> None:
    """Test that get_drive_id raises NoLibraryError when no matching drive exists."""
    headers = {"Authorization": "Bearer fake-token"}

    with (
        patch(
            "requests.get", return_value=utils.mock_drive_id_response(content)
        ) as mock_get,
        pytest.raises(NoLibraryError),
    ):
        auth.get_drive_id(SP_SITE_ID, SP_LIBRARY, headers)

    assert mock_get.call_count == 1
    assert (
        mock_get.call_args[0][0]
        == f"https://graph.microsoft.com/v1.0/sites/{SP_SITE_ID}/drives"
    )
    assert mock_get.call_args[1]["headers"] == headers
    assert mock_get.call_args[1]["timeout"] == 30
