"""Authentication utilities for the SharePoint connector."""

from azure.identity import ClientSecretCredential

from connector.constants import SCOPE
from connector.exceptions import NoLibraryError
from connector.utils import request_with_retry


def get_azure_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """Obtain an Azure token using client credentials.

    Args:
        tenant_id (str): The Azure tenant ID.
        client_id (str): The Azure client ID.
        client_secret (str): The Azure client secret.

    Returns:
        str: The Azure token.

    """
    credential = ClientSecretCredential(tenant_id, client_id, client_secret)
    return credential.get_token(SCOPE).token


def get_drive_id(site_id: str, library_name: str, headers: dict[str, str]) -> str:
    """Fetch the ID of a SharePoint document library.

    Args:
        site_id (str): The ID of the SharePoint site.
        library_name (str): The name of the document library.
        headers (dict[str, str]): The headers to use for the request, including
            authorization.

    Returns:
        str: The ID of the document library.

    Raises:
        NoLibraryError: If the library is not found on the site.

    """
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drives"
    response = request_with_retry("GET", url, headers=headers, timeout=30)
    response.raise_for_status()
    drives = response.json().get("value", [])
    for drive in drives:
        if drive["name"] == library_name:
            return drive["id"]  # type: ignore[no-any-return]
    err = f"Library '{library_name}' not found on site '{site_id}'"
    raise NoLibraryError(err)
