"""SharePoint connector for handling interactions with Microsoft Graph API."""

import logging
from io import BytesIO
from pathlib import Path
from typing import Any
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
from connector.exceptions import UploadError
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

    def model_post_init(self, _: Any) -> None:  # noqa: ANN401
        """Post-initialization to set up SharePoint-specific attributes."""
        self.set_graph_headers()
        self.set_drive_id()

    def set_graph_headers(self) -> None:
        """Obtain Azure token and generate headers for the sharepoint App."""
        log.info("Requesting Azure Graph API token...")

        token = auth.get_azure_token(
            str(self.secrets.SECRET_AZURE_TENANT_ID),
            self.secrets.SECRET_AZURE_CLIENT_ID.get_secret_value(),
            self.secrets.SECRET_AZURE_CLIENT_SECRET.get_secret_value(),
        )

        log.info("Successfully retrieved Azure Graph API token.")

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
            raise UploadError(err)
        return site_id

    def set_drive_id(self) -> None:
        """Fetch the drive ID for the specified SharePoint library.

        Args:
            headers (dict[str, str]): The headers to use for the request..

        Raises:
            UploadError: If the drive ID cannot be retrieved due to an HTTP error or if
                the specified library is not found on the site.

        """
        log.info(
            "Fetching drive ID for library '%s' in site '%s'...",
            self.library.library,
            self.library.site,
        )
        try:
            site_id = self.get_site_id()
            drive_id = auth.get_drive_id(
                site_id,
                self.library.library,
                self.headers,
            )
            log.info("Found drive ID")

            self.drive_id = drive_id
        except (requests.HTTPError, ValueError) as exc:
            raise UploadError(str(exc)) from exc

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

        """
        log.info("Creating SharePoint upload URL...")

        session_body = {
            "item": {
                "@microsoft.graph.conflictBehavior": "replace",
                "name": Path(self.file_path).name,
            }
        }
        upload_session_url = f"{self.base_url}/createUploadSession"
        session_resp = request_with_retry(
            "POST",
            upload_session_url,
            headers=self.headers,
            json=session_body,
            timeout=30,
        )

        session_resp.raise_for_status()
        url = session_resp.json()["uploadUrl"]

        log.info("Upload session created successfully.")

        self.upload_url = url

    def set_download_url(self) -> None:
        """Generate the source SharePoint url to download from.

        Args:
            None

        Returns:
            None

        """
        log.info("Creating SharePoint download URL...")

        self.download_url = f"{self.base_url}/content"

    def fetch_file(self) -> bytes:
        """Fetch a file from SharePoint.

        Returns:
            bytes: The content of the file.

        Raises:
            UploadError: If the file cannot be fetched due to an HTTP error or if the
                        specified file is not found in SharePoint.

        """
        log.info("Fetching file from SharePoint...")

        try:
            file_resp = request_with_retry(
                "GET",
                self.download_url,
                headers=self.headers,
                timeout=30,
            )
            if file_resp.status_code == DOES_NOT_EXIST_CODE:
                err = f"File not found in SharePoint: '{self.file_path}'"
                raise UploadError(err)

            file_resp.raise_for_status()
            return file_resp.content  # noqa: TRY300

        except requests.RequestException as exc:
            err = f"Failed to fetch file from SharePoint: {exc}"
            raise UploadError(err) from exc

    def verify_uploaded_file(self, expected_size: int) -> None:
        """Verify that the file was uploaded successfully to SharePoint.

        Args:
            expected_size (int): Expected size in bytes for the uploaded file.

        Returns:
            None

        """
        expected_name = Path(self.file_path).name
        verify_url = f"{self.base_url}?$select=name,size,file"
        try:
            resp = request_with_retry(
                "GET", verify_url, headers=self.headers, timeout=30
            )
            if resp.status_code == DOES_NOT_EXIST_CODE:
                err = (
                    f"Verification failed: file '{expected_name}'"
                    " not found in SharePoint."
                )
                raise UploadError(err)
            resp.raise_for_status()
            item = resp.json()
            if "file" not in item or item.get("size") != expected_size:
                err = (
                    f"Verification failed: file '{expected_name}' not found with size "
                    f"{expected_size} bytes."
                )
                raise UploadError(err)
            log.info(
                "Verified uploaded file '%s' (%s bytes)",
                expected_name,
                expected_size,
            )
        except requests.RequestException as exc:
            err = f"Failed to verify uploaded file: {exc}"
            raise UploadError(err) from exc

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

        """
        session = build_retry_session()

        start = self.get_next_start(session=session)
        file.seek(start)

        last_logged_pct = -10
        chunk_retries = 0
        while start < file_size:
            remaining = file_size - start
            chunk_size = CHUNK_SIZE if CHUNK_SIZE > 0 else remaining
            to_read = min(chunk_size, remaining)
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
                    raise UploadError(err) from exc
                log.warning("Chunk upload failed, attempting to resume...")
                resume_at = self.get_next_start(session=session)
                if resume_at != start:
                    log.info("Resuming from %s after partial upload", f"{resume_at:,}")
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
                raise UploadError(err)

            # Transient server errors (429, 5xx): attempt resume
            if r.status_code >= BAD_REQUEST_CODE:
                chunk_retries += 1
                if chunk_retries > MAX_CHUNK_RETRIES:
                    err = (
                        f"Chunk upload failed with HTTP {r.status_code}"
                        f" after {MAX_CHUNK_RETRIES} retries"
                    )
                    raise UploadError(err)
                log.warning("Chunk upload failed, attempting to resume...")
                resume_at = self.get_next_start(session=session)
                if resume_at != start:
                    log.info("Resuming from %s after partial upload", f"{resume_at:,}")
                    start = resume_at
                file.seek(start)
                continue

            start += len(chunk)
            chunk_retries = 0
            pct = int((start / file_size) * 100)
            if pct // 10 > last_logged_pct // 10:
                log.info(
                    "Uploaded %s/%s bytes (%s%%)",
                    f"{start:,}",
                    f"{file_size:,}",
                    pct,
                )
                last_logged_pct = pct

        self.verify_uploaded_file(expected_size=file_size)
