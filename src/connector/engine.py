"""Engine module for handling file transfers between S3 and SharePoint."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

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
    """Abstract base class for different storage engines.

    This class provides a common interface for engines that handle file transfers
    between S3 and SharePoint. Subclasses must implement methods for listing,
    downloading, uploading, and deleting files, as well as validating transfer plans.

    Methods:
        list_source_files: List files available in the source storage.
        download_file: Download a file from the source storage.
        upload_file: Upload a file to the destination storage.
        delete_source_file: Delete a file from the source storage after successful
            transfer.
        validate_plan: Validate planned file movement is feasible before execution.
        run: Transfer a single file from source to destination storage.

    """

    secrets: SecretConfig
    library: SharePointLibrary
    bucket: S3Bucket
    sharepoint_connector: SharePointConnector = field(init=False)
    s3_connector: S3Connector = field(init=False)
    s3_client: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Post-initialization to create S3 and SharePoint connectors."""
        log.info("Setting up storage connectors...")
        self.s3_client = boto3.client("s3")
        self.sharepoint_connector = SharePointConnector(
            secrets=self.secrets, library=self.library
        )
        self.s3_connector = S3Connector(
            client=self.s3_client, bucket=self.bucket.bucket
        )

    @abstractmethod
    def list_source_files(self) -> list[str]:
        """List files available in the source storage."""

    @abstractmethod
    def download_file(self, source: str) -> bytes:
        """Download a file from the source storage."""

    @abstractmethod
    def upload_file(self, content: bytes, destination: str) -> None:
        """Upload a file to the destination storage."""

    @abstractmethod
    def delete_source_file(self, source: str) -> None:
        """Delete a file from the source storage after successful transfer."""

    @abstractmethod
    def validate_plan(self, source: str, destination: str) -> None:
        """Validate planned file movement is feasible before execution.

        Args:
            source (str): Source file path (S3 key or SharePoint path).
            destination (str): Destination file path (SharePoint path or S3 key).

        Raises:
            UploadError: If one or more validation checks fail.

        """

    def run(self, source: str, destination: str, *, delete: bool = False) -> None:
        """Transfer a single file from source to destination storage.

        Args:
            source (str): Source file path (S3 key or SharePoint path).
            destination (str): Destination file path (SharePoint path or S3 key).
            delete (bool): Whether to delete the source file after a successful
                transfer.

        Raises:
            UploadError: If the download or upload step fails.

        Source is the full S3 key (excluding the bucket name) or the full path to the
        SharePoint file (excluding the site and library). Destination is the full path
        to the SharePoint file (excluding the site and library) or the full S3 key
        (excluding the bucket name).

        Setting 'delete' will remove the source file after a successful transfer.

        """
        log.info("Validating movement plan")
        self.validate_plan(source=source, destination=destination)
        log.info("Starting transfer: '%s' -> '%s'", source, destination)
        content = self.download_file(source)
        self.upload_file(content, destination)
        log.info(
            "Transfer complete: '%s' -> '%s' (%s bytes)",
            source,
            destination,
            len(content),
        )
        if delete:
            log.info("Deleting source file '%s'...", source)
            self.delete_source_file(source)
            log.info("Source file '%s' deleted.", source)


class UploadToSharePointEngine(Engine):
    """Engine for uploading files from S3 to SharePoint.

    Methods:
        list_source_files: List files available in the S3 source bucket.
        download_file: Download a file from the S3 source bucket.
        upload_file: Upload a file to the SharePoint destination.
        delete_source_file: Delete a file from the S3 source bucket after successful
            transfer.
        validate_plan: Validate planned file movement is feasible before execution.
        run: Transfer a single file from S3 to SharePoint.

    """

    def list_source_files(self) -> list[str]:
        """List all object keys in the S3 source bucket."""
        return self.s3_connector.list_objects()

    def validate_plan(self, source: str, destination: str) -> None:
        """Validate planned file movement is feasible before execution.

        Validates that:

        - The S3 source bucket is accessible.
        - The source S3 key exists.
        - The destination SharePoint parent folder exists.

        Args:
            source (str): Source file path (S3 key).
            destination (str): Destination file path (SharePoint path).

        Raises:
            UploadError: If one or more validation checks fail.

        """
        log.info("Validating source: '%s' and destination: '%s'", source, destination)
        errors: list[str] = []

        try:
            self.s3_connector.check_bucket_exists()
        except UploadError as exc:
            errors.append(str(exc))

        try:
            self.s3_connector.update_with_key(source)
            self.s3_connector.check_object_exists()
        except UploadError as exc:
            errors.append(str(exc))

        folder = str(Path(destination).parent)
        if folder and folder != ".":
            try:
                self.sharepoint_connector.check_object_exists(folder, "folder")
            except UploadError as exc:
                errors.append(str(exc))

        if errors:
            all_errors = "\n".join(f"  - {e}" for e in errors)
            err = f"Validation failed with {len(errors)} error(s):\n {all_errors}"
            raise UploadError(err)

        log.info("Validation passed.")

    def download_file(self, source: str) -> bytes:
        """Download a file from S3 and return its content as bytes.

        Args:
            source (str): The source S3 key.

        Returns:
            bytes: The content of the S3 object as bytes.

        Raises:
            UploadError: If the S3 download fails.

        """
        log.info("Downloading s3://%s/%s...", self.bucket.bucket, source)
        self.s3_connector.update_with_key(source)
        return self.s3_connector.download_from_s3()

    def upload_file(self, content: bytes, destination: str) -> None:
        """Upload a file to SharePoint.

        Args:
            content (bytes): The content of the file to upload as bytes.
            destination (str): The destination path in SharePoint.

        Raises:
            UploadError: If the SharePoint upload or verification fails.

        """
        log.info(
            "Uploading %s bytes to SharePoint path '%s'...", len(content), destination
        )
        self.sharepoint_connector.update_with_file_path(destination)
        self.sharepoint_connector.set_upload_url()
        self.sharepoint_connector.upload_stream_in_chunks(
            BytesIO(content), len(content)
        )
        self.sharepoint_connector.verify_uploaded_file(expected_size=len(content))

    def delete_source_file(self, source: str) -> None:
        """Delete a file from S3."""
        log.info("Deleting source file s3://%s/%s...", self.bucket.bucket, source)
        self.s3_connector.update_with_key(source)
        self.s3_connector.delete_object()
        log.info("Source file s3://%s/%s deleted.", self.bucket.bucket, source)


class UploadToS3Engine(Engine):
    """Engine for uploading files from SharePoint to S3.

    Methods:
       list_source_files: List files available in the S3 source bucket.
       download_file: Download a file from the S3 source bucket.
       upload_file: Upload a file to the SharePoint destination.
       delete_source_file: Delete a file from the S3 source bucket after successful
            transfer.
       validate_plan: Validate planned file movement is feasible before execution.
       run: Transfer a single file from S3 to SharePoint.

    """

    def list_source_files(self) -> list[str]:
        """List all file paths in the SharePoint source library."""
        return self.sharepoint_connector.list_files()

    def validate_plan(self, source: str, destination: str) -> None:
        """Validate planned file movement is feasible before execution.

        Validates that:

        - The S3 destination bucket is accessible.
        - The source file exists in SharePoint.

        All errors are collected before raising, so the caller receives a single
        report of every problem.

        Args:
            source (str): Source file path (SharePoint path).
            destination (str): Destination file path (S3 key).

        Raises:
            UploadError: If one or more validation checks fail.

        """
        log.info("Validating source: '%s' and destination: '%s'", source, destination)
        errors: list[str] = []

        try:
            self.s3_connector.check_bucket_exists()
        except UploadError as exc:
            errors.append(str(exc))

        try:
            self.sharepoint_connector.check_object_exists(source, "file")
        except UploadError as exc:
            errors.append(str(exc))

        if errors:
            all_errors = "\n".join(f"  - {e}" for e in errors)
            err = f"Validation failed with {len(errors)} error(s):\n {all_errors}"
            raise UploadError(err)

        log.info("Validation passed.")

    def download_file(self, source: str) -> bytes:
        """Download a file from SharePoint and return its content as bytes.

        Args:
            source (str): The source path in SharePoint.

        Returns:
            bytes: The content of the SharePoint file as bytes.

        Raises:
            UploadError: If the SharePoint download fails.

        """
        log.info(
            "Downloading '%s' from SharePoint library '%s'...",
            source,
            self.library.library,
        )
        self.sharepoint_connector.update_with_file_path(source)
        self.sharepoint_connector.set_download_url()
        return self.sharepoint_connector.fetch_file()

    def upload_file(self, content: bytes, destination: str) -> None:
        """Upload a file to S3 and verify the uploaded object.

        Args:
            content (bytes): The content of the file to upload as bytes.
            destination (str): The destination S3 key.

        Raises:
            UploadError: If the S3 upload or verification fails.

        """
        log.info(
            "Uploading %s bytes to s3://%s/%s...",
            len(content),
            self.bucket.bucket,
            destination,
        )
        self.s3_connector.update_with_key(destination)
        self.s3_connector.upload_to_s3(content)
        self.s3_connector.verify_uploaded_object(expected_size=len(content))
        log.info("S3 upload verification succeeded.")

    def delete_source_file(self, source: str) -> None:
        """Delete a file from SharePoint."""
        log.info("Deleting source file '%s' from SharePoint...", source)
        self.sharepoint_connector.update_with_file_path(source)
        self.sharepoint_connector.delete_file()
        log.info("Source file '%s' deleted from SharePoint.", source)
