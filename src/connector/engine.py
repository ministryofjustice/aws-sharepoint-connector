"""Engine module for handling file transfers between S3 and SharePoint."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from io import BytesIO

import boto3

from connector.config import (
    S3Bucket,
    SecretConfig,
    SharePointLibrary,
)
from connector.exceptions import UploadError
from connector.s3 import S3Connector
from connector.sharepoint import SharePointConnector
from connector.utils import setup_logger

log = setup_logger()


@dataclass
class Engine(ABC):
    """Abstract base class for different storage engines."""

    secrets: SecretConfig
    library: SharePointLibrary
    bucket: S3Bucket
    sharepoint_connector: SharePointConnector = field(init=False)

    @abstractmethod
    def download_file(self, source: str) -> bytes:
        """Download a file from the source storage."""

    @abstractmethod
    def upload_file(self, content: bytes, destination: str) -> None:
        """Upload a file to the destination storage."""

    def __post_init__(self) -> None:
        """Post-initialization to create SharePointConnector and S3Connector."""
        log.info("Setting up storage connectors...")
        self.sharepoint_connector = SharePointConnector(
            secrets=self.secrets, library=self.library
        )


class UploadToSharePointEngine(Engine):
    """Engine for uploading files to SharePoint."""

    def download_file(self, source: str) -> bytes:
        """Download a file from S3 and return its content as bytes.

        Args:
            source (str): The source S3 key.

        Returns:
            bytes: The content of the S3 object as bytes.

        """
        log.info("Downloading file from S3...")
        s3_connector = S3Connector(
            client=boto3.client("s3"),
            bucket=self.bucket.bucket,
            key=source,
        )
        return s3_connector.download_from_s3()

    def upload_file(self, content: bytes, destination: str) -> None:
        """Upload a file to SharePoint.

        Args:
            content (bytes): The content of the file to upload as bytes.
            destination (str): The destination path in SharePoint.

        Returns:
            None

        """
        log.info("Uploading %s bytes to SharePoint...", len(content))
        self.sharepoint_connector.update_with_file_path(destination)
        self.sharepoint_connector.set_upload_url()
        self.sharepoint_connector.upload_stream_in_chunks(
            BytesIO(content), len(content)
        )

    def run(self, source: str, destination: str) -> None:
        """Run the engine to transfer a file from S3 to SharePoint."""
        content = self.download_file(source)
        self.upload_file(content, destination)


class UploadToS3Engine(Engine):
    """Engine for uploading files to S3."""

    def download_file(self, source: str) -> bytes:
        """Download a file from SharePoint and return its content as bytes.

        Args:
            source (str): The source path in SharePoint.

        Returns:
            bytes: The content of the SharePoint file as bytes.

        """
        try:
            log.info("Downloading file from SharePoint...")
            self.sharepoint_connector.update_with_file_path(source)
            self.sharepoint_connector.set_download_url()
            return self.sharepoint_connector.fetch_file()
        except UploadError:
            raise
        except Exception as exc:
            err = f"Failed to download file from SharePoint: {exc}"
            raise UploadError(err) from exc

    def upload_file(self, content: bytes, destination: str) -> None:
        """Upload a file to S3 and verify the uploaded object.

        Args:
            content (bytes): The content of the file to upload as bytes.
            destination (str): The destination path in S3.

        Returns:
            None

        """
        log.info(
            "Uploading %s bytes to S3 bucket '%s' with key '%s'...",
            len(content),
            self.bucket.bucket,
            destination,
        )
        s3_connector = S3Connector(
            client=boto3.client("s3"),
            bucket=self.bucket.bucket,
            key=destination,
        )
        s3_connector.upload_to_s3(content)
        s3_connector.verify_uploaded_object(expected_size=len(content))
        log.info("S3 upload verification succeeded.")
