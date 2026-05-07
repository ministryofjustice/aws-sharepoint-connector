"""Engine module for handling file transfers between S3 and SharePoint."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from io import BytesIO

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from connector.config import SecretConfig, S3ToSPMovementPlan, SPToS3MovementPlan
from connector.exceptions import UploadError
from connector.s3 import S3Connector
from connector.sharepoint import SharePointConnector
from connector.utils import setup_logger

log = setup_logger()


@dataclass
class Engine(ABC):
    """Abstract base class for different storage engines."""

    config: SecretConfig
    movement_plan: S3ToSPMovementPlan | SPToS3MovementPlan
    sharepoint_connector: SharePointConnector = field(init=False)
    s3_connector: S3Connector = field(init=False)

    @abstractmethod
    def download_file(self) -> bytes:
        """Download a file from the source storage."""

    @abstractmethod
    def upload_file(self, content: bytes) -> None:
        """Upload a file to the destination storage."""

    def __post_init__(self) -> None:
        """Post-initialization to create SharePointConnector and S3Connector."""
        log.info("Setting up storage connectors...")
        self.sharepoint_connector = SharePointConnector(config=self.config)
        self.s3_connector = S3Connector(
            client=boto3.client("s3"),
            bucket=self.config.S3_BUCKET,
            key=self.config.FILE_KEY,
        )


class UploadToSharePointEngine(Engine):
    """Engine for uploading files to SharePoint."""

    movement_plan: S3ToSPMovementPlan

    def download_file(self) -> bytes:
        """Download a file from S3 and return its content as bytes.

        Args:
            None

        Returns:
            bytes: The content of the S3 object as bytes.

        """
        try:
            log.info("Downloading file from S3...")
            return self.s3_connector.download_from_s3()
        except (BotoCoreError, ClientError) as exc:
            err = f"Failed to download {self.config.FILE_KEY} from S3: {exc}"
            raise UploadError(err) from exc

    def upload_file(self, content: bytes) -> None:
        """Upload a file to SharePoint.

        Args:
            content (bytes): The content of the file to upload as bytes.

        Returns:
            None

        """
        log.info("Uploading %s bytes to SharePoint...", len(content))
        self.sharepoint_connector.create_upload_url()
        self.sharepoint_connector.upload_stream_in_chunks(
            BytesIO(content), len(content)
        )


class UploadToS3Engine(Engine):
    """Engine for uploading files to S3."""

    movement_plan: SPToS3MovementPlan

    def download_file(self) -> bytes:
        """Download a file from SharePoint and return its content as bytes.

        Args:
            None

        Returns:
            bytes: The content of the SharePoint file as bytes.

        """
        try:
            log.info("Downloading file from SharePoint...")
            self.sharepoint_connector.create_download_url()
            return self.sharepoint_connector.fetch_file()
        except UploadError:
            raise
        except Exception as exc:
            err = f"Failed to download file from SharePoint: {exc}"
            raise UploadError(err) from exc

    def upload_file(self, content: bytes) -> None:
        """Upload a file to S3 and verify the uploaded object.

        Args:
            content (bytes): The content of the file to upload as bytes.

        Returns:
            None

        """
        log.info(
            "Uploading %s bytes to S3 bucket '%s' with key '%s'...",
            len(content),
            self.config.S3_BUCKET,
            self.config.FILE_KEY,
        )
        self.s3_connector.upload_to_s3(content)
        self.s3_connector.verify_uploaded_object(expected_size=len(content))
        log.info("S3 upload verification succeeded.")
