"""SharePoint connector for handling interactions with Microsoft Graph API."""

import logging
from io import BytesIO
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import requests
from pydantic import BaseModel, Field

from connector import auth
from connector.config import (
    SecretConfig,
    SharePointLibrary,
)
from connector.constants import (
    BAD_REQUEST_CODE,
    CHUNK_SIZE,
    DOES_NOT_EXIST_CODE,
    MAX_CHUNK_RETRIES,
    SERVER_ERROR_CODE,
    SHAREPOINT_DOMAIN,
    TOO_MANY_REQUESTS_CODE,
)
from connector.exceptions import (
    FileSizeMismatchError,
    IncorrectObjectTypeError,
    NoLibraryError,
    NoSiteError,
    ObjectNotFoundError,
    ProcessingError,
)
from connector.utils import build_retry_session, request_with_retry

log = logging.getLogger("s3-sharepoint")


class SharePointConnector(BaseModel):
    """Connector for interacting with SharePoint via Microsoft Graph API."""

    secrets: SecretConfig
    library: SharePointLibrary
    headers: dict[str, str] = Field(default_factory=dict, init=False)
    drive_id: str = Field(default="", init=False)
    base_url: str = Field(default="", init=False)
    upload_url: str = Field(default="", init=False)
    download_url: str = Field(default="", init=False)
    file_path: str = Field(default="", init=False)
    archive_url: str = Field(default="", init=False)

    def model_post_init(self, _: Any) -> None:  # noqa: ANN401
        """Post-initialization to set up SharePoint-specific attributes."""
        self.set_graph_headers()
        self.set_drive_id()

    def set_graph_headers(self) -> None:
        """Obtain Azure token and generate headers for the sharepoint App."""
        log.info("Authenticating SharePoint connector with Azure Graph API.")

        token = auth.get_azure_token(
            str(self.secrets.SECRET_AZURE_TENANT_ID),
            self.secrets.SECRET_AZURE_CLIENT_ID.get_secret_value(),
            self.secrets.SECRET_AZURE_CLIENT_SECRET.get_secret_value(),
        )

        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }

    def get_site_id(self) -> str:
        """Fetch the SharePoint site ID using the Graph API.

        Args:
            None

        Returns:
            str: The ID of the SharePoint site.

        Raises:
            NoSiteError: If the site ID cannot be retrieved or the site is unreachable.

        """
        site_path = f"/sites/{self.library.site}"

        site_url = (
            f"https://graph.microsoft.com/v1.0/sites/{SHAREPOINT_DOMAIN}{site_path}"
        )

        site_response = request_with_retry(
            "GET", site_url, headers=self.headers, timeout=60
        )

        site_response.raise_for_status()

        site_id: str | None = site_response.json().get("id")
        if site_id is None:
            err = f"Graph API returned no site ID for '{self.library.site}'"
            raise NoSiteError(err)
        return site_id

    def set_drive_id(self) -> None:
        """Fetch the drive ID for the specified SharePoint library.

        Raises:
            ProcessingError: If the drive ID cannot be retrieved, the site is
                unreachable, or the specified library is not found on the site.

        """
        try:
            site_id = self.get_site_id()
            drive_id = auth.get_drive_id(
                site_id,
                self.library.library,
                self.headers,
            )
            log.info(
                "Resolved SharePoint drive ID for library '%s' in site '%s'.",
                self.library.library,
                self.library.site,
            )
            self.drive_id = drive_id
        except (requests.HTTPError, ValueError, NoLibraryError) as exc:
            err = (
                f"Could not connect to SharePoint library '{self.library.library}' "
                f"in site '{self.library.site}': {exc}"
            )
            raise ProcessingError(err) from exc

    def set_base_url(self) -> None:
        """Generate the base URL for the target file in SharePoint.

        Args:
            None

        Returns:
            None

        """
        encoded_path = quote(self.file_path, safe="/")
        self.base_url = f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/root:/{encoded_path}:"

    def update_with_file_path(self, file_path: str) -> None:
        """Update the connector with the target file path and regenerate URLs.

        Args:
            file_path (str): The target file path in SharePoint.

        Returns:
            None

        """
        self.file_path = file_path
        self.set_base_url()

    def set_upload_url(self) -> None:
        """Generate the target SharePoint url for uploading to.

        Args:
            None

        Returns:
            None

        Raises:
            ProcessingError: If the upload session cannot be created due to an HTTP
                error or if the specified library is not found on the site.

        """
        session_body = {
            "item": {
                "@microsoft.graph.conflictBehavior": "replace",
                "name": Path(self.file_path).name,
            }
        }
        upload_session_url = f"{self.base_url}/createUploadSession"
        try:
            session_resp = request_with_retry(
                "POST",
                upload_session_url,
                headers=self.headers,
                json=session_body,
                timeout=30,
            )
        except (ValueError, requests.RequestException) as exc:
            err = f"Failed to create SharePoint upload session: {exc}"
            raise ProcessingError(err) from exc

        session_resp.raise_for_status()
        url = session_resp.json()["uploadUrl"]

        log.info(
            "Created SharePoint upload session for '%s'.",
            self.file_path,
        )

        self.upload_url = url

    def set_download_url(self) -> None:
        """Generate the source SharePoint url to download from.

        Args:
            None

        Returns:
            None

        """
        self.download_url = f"{self.base_url}/content"

    def set_archive_url(self, archive_folder: str) -> None:
        """Generate the target SharePoint url for archiving files.

        Args:
            archive_folder (str): The archive destination folder in SharePoint.

        Returns:
            None

        """
        archive_path = str(Path(archive_folder) / Path(self.file_path).name)
        encoded_path = quote(archive_path, safe="/")
        self.archive_url = f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}/root:/{encoded_path}:/content"

    def list_files(self) -> list[str]:
        """List all files in the SharePoint library, including subfolders.

        Handles pagination automatically at every folder level.

        Returns:
            list[str]: File paths relative to the library root.

        Raises:
            ProcessingError: If the listing request fails.

        """
        root_url = (
            f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}"
            f"/root/children?$select=name,folder"
        )
        file_paths: list[str] = []

        folder_paths: list[str] = [""]

        def children_url(folder_path: str) -> str:
            if not folder_path:
                return root_url
            encoded_path = quote(folder_path, safe="/")
            return (
                f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}"
                f"/root:/{encoded_path}:/children?$select=name,folder"
            )

        try:
            while folder_paths:
                folder_path = folder_paths.pop(0)
                next_url: str | None = children_url(folder_path)

                while next_url:
                    resp = request_with_retry(
                        "GET",
                        next_url,
                        headers=self.headers,
                        timeout=30,
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    for item in data.get("value", []):
                        name = item["name"]
                        item_path = f"{folder_path}/{name}" if folder_path else name
                        if "folder" in item:
                            folder_paths.append(item_path)
                        else:
                            file_paths.append(item_path)

                    next_url = data.get("@odata.nextLink")
        except requests.RequestException as exc:
            err = (
                f"Failed to list files in SharePoint library '{self.library.library}' "
                f"on site '{self.library.site}': {exc}"
            )
            raise ProcessingError(err) from exc
        log.info(
            "Listed %d file(s) in SharePoint library '%s' on site '%s'.",
            len(file_paths),
            self.library.library,
            self.library.site,
        )
        return file_paths

    def check_object_exists(
        self, path: str, obj_type: Literal["file", "folder"]
    ) -> None:
        """Check that an object exists in SharePoint before attempting to access it.

        Args:
            path (str): The path within the SharePoint library.
            obj_type (Literal["file", "folder"]): The expected type of the object.

        Raises:
            IncorrectObjectTypeError: If the object exists but is not of expected type.
            ObjectNotFoundError: If the object does not exist in SharePoint.
            ProcessingError: If the object does not exist, the path resolves to a
                different type, or the request fails.

        """
        encoded_path = quote(path, safe="/")
        check_url = (
            f"https://graph.microsoft.com/v1.0/drives/{self.drive_id}"
            f"/root:/{encoded_path}:?$select=name,{obj_type}"
        )
        try:
            resp = request_with_retry(
                "GET", check_url, headers=self.headers, timeout=30
            )
        except requests.RequestException as exc:
            err = f"Failed to check SharePoint {obj_type} existence for '{path}': {exc}"
            raise ProcessingError(err) from exc

        if resp.status_code == DOES_NOT_EXIST_CODE:
            err = f"{obj_type.capitalize()} not found in SharePoint: '{path}'"
            raise ObjectNotFoundError(err)
        resp.raise_for_status()
        item = resp.json()
        if obj_type not in item:
            err = f"SharePoint path '{path}' exists but is not a {obj_type}"
            raise IncorrectObjectTypeError(err)

    def fetch_file(self) -> bytes:
        """Fetch a file from SharePoint.

        Returns:
            bytes: The content of the file.

        Raises:
            ObjectNotFoundError: If the specified file is not found in SharePoint.
            ProcessingError: If the file cannot be fetched due to an HTTP error or if
                the specified file is not found in SharePoint.

        """
        try:
            file_resp = request_with_retry(
                "GET",
                self.download_url,
                headers=self.headers,
                timeout=30,
            )
        except requests.RequestException as exc:
            err = f"Failed to fetch file from SharePoint: {exc}"
            raise ProcessingError(err) from exc

        if file_resp.status_code == DOES_NOT_EXIST_CODE:
            err = f"File not found in SharePoint: '{self.file_path}'"
            raise ObjectNotFoundError(err)
        file_resp.raise_for_status()
        return file_resp.content

    def verify_uploaded_file(
        self, expected_size: int, verify_type: Literal["destination", "archive"]
    ) -> None:
        """Verify that the file was uploaded successfully to SharePoint.

        Args:
            expected_size (int): Expected size in bytes for the uploaded file.
            verify_type (Literal["destination", "archive"]): Object being verified.

        Returns:
            None

        Raises:
            FileSizeMismatchError: If the uploaded file does not match expected size.
            ObjectNotFoundError: If the uploaded file is not found in SharePoint.
            ProcessingError: If the verification request fails.

        """
        expected_name = Path(self.file_path).name

        if verify_type == "destination":
            verify_url = f"{self.base_url}?$select=name,size,file"
        else:
            archive_item_url = self.archive_url.removesuffix("/content")
            verify_url = f"{archive_item_url}?$select=name,size,file"

        try:
            resp = request_with_retry(
                "GET", verify_url, headers=self.headers, timeout=30
            )
        except requests.RequestException as exc:
            err = f"Failed to verify uploaded file: {exc}"
            raise ProcessingError(err) from exc

        if resp.status_code == DOES_NOT_EXIST_CODE:
            err = (
                f"Verification failed: file '{expected_name}' not found in SharePoint."
            )
            raise ObjectNotFoundError(err)
        resp.raise_for_status()
        item = resp.json()
        if "file" not in item or item.get("size") != expected_size:
            err = (
                f"Verification failed: file '{expected_name}' not found with size "
                f"{expected_size} bytes."
            )
            raise FileSizeMismatchError(err)
        log.info(
            "Verified SharePoint upload for '%s' (%s bytes).",
            expected_name,
            expected_size,
        )

    def get_next_start(self, session: requests.Session) -> int:
        """Get the next starting byte position for uploading a chunk.

        Args:
            session (requests.Session): The requests session to use for the request.

        Returns:
            int: The next starting byte position for uploading.

        """
        st = session.get(self.upload_url, timeout=(10, 60))
        st.raise_for_status()
        info = st.json()
        ranges = info.get("nextExpectedRanges") or ["0-"]
        start_str = ranges[0].split("-")[0]
        return int(start_str)

    def put_chunk(
        self, start: int, data: bytes, file_size: int, session: requests.Session
    ) -> requests.Response:
        """Upload a chunk of data to SharePoint.

        Args:
            start (int): The starting byte position of the chunk.
            data (bytes): The chunk of data to upload.
            file_size (int): The total size of the file being uploaded.
            session (requests.Session): The requests session to use for the upload.

        Returns:
            requests.Response: The response from the upload request.

        """
        end = start + len(data) - 1
        h = {
            "Content-Length": str(len(data)),
            "Content-Range": f"bytes {start}-{end}/{file_size}",
        }
        return session.put(self.upload_url, headers=h, data=data, timeout=(10, 300))

    def upload_stream_in_chunks(
        self,
        file: BytesIO,
        file_size: int,
    ) -> None:
        """Upload a file to SharePoint in chunks.

        Args:
            file (BytesIO): The file-like object containing the data to upload.
            file_size (int): The total size of the file being uploaded.

        Returns:
            None

        Raises:
            ProcessingError: If the upload fails.

        """
        session = build_retry_session()

        start = self.get_next_start(session=session)
        file.seek(start)

        last_logged_pct = -10
        chunk_retries = 0
        while start < file_size:
            remaining = file_size - start
            to_read = min(CHUNK_SIZE, remaining)
            chunk = file.read(to_read)
            try:
                r = self.put_chunk(
                    start=start,
                    data=chunk,
                    file_size=file_size,
                    session=session,
                )
            except requests.exceptions.RequestException as exc:
                chunk_retries += 1
                if chunk_retries > MAX_CHUNK_RETRIES:
                    err = (
                        f"Chunk upload failed after {MAX_CHUNK_RETRIES} retries: {exc}"
                    )
                    raise ProcessingError(err) from exc
                log.warning(
                    (
                        "SharePoint chunk upload failed due to network error;"
                        " attempting resume (retry %s/%s).",
                    ),
                    chunk_retries,
                    MAX_CHUNK_RETRIES,
                )
                resume_at = self.get_next_start(session=session)
                if resume_at != start:
                    log.info(
                        "Resuming SharePoint chunk upload from byte %s.",
                        f"{resume_at:,}",
                    )
                    start = resume_at
                file.seek(start)
                continue

            # Permanent 4xx client errors (excluding 429) must not be retried
            is_permanent_error = (
                BAD_REQUEST_CODE <= r.status_code < SERVER_ERROR_CODE
                and r.status_code != TOO_MANY_REQUESTS_CODE
            )
            if is_permanent_error:
                err = f"Chunk upload failed with permanent HTTP {r.status_code} error"
                raise ProcessingError(err)

            # Transient server errors (429, 5xx): attempt resume
            if r.status_code >= BAD_REQUEST_CODE:
                chunk_retries += 1
                if chunk_retries > MAX_CHUNK_RETRIES:
                    err = (
                        f"Chunk upload failed with HTTP {r.status_code}"
                        f" after {MAX_CHUNK_RETRIES} retries"
                    )
                    raise ProcessingError(err)
                log.warning(
                    (
                        "SharePoint chunk upload returned HTTP %s;"
                        " attempting resume (retry %s/%s).",
                    ),
                    r.status_code,
                    chunk_retries,
                    MAX_CHUNK_RETRIES,
                )
                resume_at = self.get_next_start(session=session)
                if resume_at != start:
                    log.info(
                        "Resuming SharePoint chunk upload from byte %s.",
                        f"{resume_at:,}",
                    )
                    start = resume_at
                file.seek(start)
                continue

            start += len(chunk)
            chunk_retries = 0
            pct = int((start / file_size) * 100)
            if pct // 10 > last_logged_pct // 10:
                log.info(
                    "SharePoint chunk upload progress: %s/%s bytes (%s%%).",
                    f"{start:,}",
                    f"{file_size:,}",
                    pct,
                )
                last_logged_pct = pct

    def delete_file(self) -> None:
        """Delete a file from SharePoint.

        Args:
            path (str): The path of the file to delete in SharePoint.

        Returns:
            None

        Raises:
            ObjectNotFoundError: If the specified file is not found in SharePoint.
            ProcessingError: If the file cannot be deleted due to an HTTP error.

        """
        delete_url = f"{self.base_url}?$select=name,file"
        try:
            resp = request_with_retry(
                "DELETE", delete_url, headers=self.headers, timeout=30
            )
        except requests.RequestException as exc:
            err = f"Failed to delete file from SharePoint: {exc}"
            raise ProcessingError(err) from exc

        if resp.status_code == DOES_NOT_EXIST_CODE:
            err = f"File not found in SharePoint for deletion: '{self.base_url}'"
            raise ObjectNotFoundError(err)
        resp.raise_for_status()
