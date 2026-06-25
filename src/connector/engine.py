"""Engine module for handling file transfers between S3 and SharePoint."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

import boto3

from connector.config import (
    S3Bucket,
    SecretConfig,
    SharePointLibrary,
)
from connector.exceptions import (
    IncorrectObjectTypeError,
    NoArchiveFolderGivenError,
    ObjectNotFoundError,
    ProcessingError,
)
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
        log.info(
            "Initialising engine '%s' for SharePoint library '%s' and S3 bucket '%s'.",
            self.__class__.__name__,
            self.library.library,
            self.bucket.bucket,
        )
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
    def upload_file(self, content: bytes, destination: str, content_size: int) -> None:
        """Upload a file to the destination storage."""

    @abstractmethod
    def archive_source_file(
        self, source: str, archive_folder: str, content_size: int
    ) -> None:
        """Archive a file in the source storage after successful transfer."""

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
            ProcessingError: If one or more validation checks fail.

        """

    def run(
        self,
        source: str,
        destination: str,
        archive_folder: str = "",
        *,
        source_handling: Literal["archive", "delete", "none"] = "none",
    ) -> None:
        """Transfer a single file from source to destination storage.

        Args:
            source (str): Source file path (S3 key or SharePoint path).
            destination (str): Destination file path (SharePoint path or S3 key).
            archive_folder (str): The SharePoint folder or S3 directory to move the
                source file to if source_handling is 'archive'. This must be a directory
                path, not a file path (i.e., in the same format as the source, without
                the file name and extension).
            source_handling (Literal["archive", "delete", "none"]): How to handle the
                 source file after a successful transfer.

        Raises:
            ProcessingError: If any step of the transfer fails, including validation,
                download, upload, or deletion of the source file.
            ObjectNotFoundError: If the source file does not exist in source storage.

        Source is the full S3 key (excluding the bucket name) or the full path to the
        SharePoint file (excluding the site and library). Destination is the full path
        to the SharePoint file (excluding the site and library) or the full S3 key
        (excluding the bucket name).

        Setting source handling to 'delete' will remove the source file.
        Setting to 'archive' will move the source file to an archive folder.

        """
        if source_handling == "archive" and not archive_folder:
            err = "archive_folder must be provided when source_handling is 'archive'."
            raise NoArchiveFolderGivenError(err)

        log.info(
            "Starting transfer workflow: '%s' -> '%s' (source_handling=%s)",
            source,
            destination,
            source_handling,
        )
        self.validate_plan(source=source, destination=destination)
        content = self.download_file(source)

        content_size = len(content)

        self.upload_file(content, destination, content_size)
        log.info(
            "Transfer workflow complete: '%s' -> '%s' (%s bytes transferred)",
            source,
            destination,
            content_size,
        )
        if source_handling == "delete":
            self.delete_source_file(source)
        if source_handling == "archive":
            self.archive_source_file(source, archive_folder, content_size)


class UploadToSharePointEngine(Engine):
    """Engine for uploading files from S3 to SharePoint.

    Methods:
        list_source_files: List files available in the S3 source bucket.
        download_file: Download a file from the S3 source bucket.
        upload_file: Upload a file to the SharePoint destination.
        delete_source_file: Delete file from S3 after successful transfer.
        archive_source_file: Archive file in the S3 after successful transfer.
        validate_plan: Validate planned file movement is feasible before execution.
        run: Transfer a single file from S3 to SharePoint.

    """

    def list_source_files(self) -> list[str]:
        """List all object keys in the S3 source bucket.

        Args:
            None

        Returns:
            list[str]: All object keys in the S3 source bucket.

        Raises:
            ProcessingError: If the listing request fails.

        """
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
            ProcessingError: If one or more validation checks fail.

        """
        log.info(
            "Validating S3->SharePoint transfer for source '%s' and destination '%s'.",
            source,
            destination,
        )
        errors: list[str] = []

        try:
            self.s3_connector.check_bucket_exists()
        except ProcessingError as exc:
            errors.append(str(exc))

        try:
            self.s3_connector.set_key(source)
            self.s3_connector.check_object_exists()
        except ProcessingError as exc:
            errors.append(str(exc))

        folder = str(Path(destination).parent)
        if folder and folder != ".":
            try:
                self.sharepoint_connector.check_object_exists(folder, "folder")
            except (
                IncorrectObjectTypeError,
                ObjectNotFoundError,
                ProcessingError,
            ) as exc:
                errors.append(str(exc))

        if errors:
            all_errors = "\n".join(f"  - {e}" for e in errors)
            err = f"Validation failed with {len(errors)} error(s):\n {all_errors}"
            raise ProcessingError(err)

        log.info("Validation complete for S3->SharePoint transfer plan.")

    def download_file(self, source: str) -> bytes:
        """Download a file from S3 and return its content as bytes.

        Args:
            source (str): The source S3 key.

        Returns:
            bytes: The content of the S3 object as bytes.

        Raises:
            ProcessingError: If the S3 download fails.

        """
        log.info("Downloading s3://%s/%s...", self.bucket.bucket, source)
        self.s3_connector.set_key(source)
        return self.s3_connector.download_from_s3()

    def upload_file(self, content: bytes, destination: str, content_size: int) -> None:
        """Upload a file to SharePoint.

        Args:
            content (bytes): The content of the file to upload as bytes.
            destination (str): The destination path in SharePoint.
            content_size (int): The size of the content in bytes.

        Raises:
            FileSizeMismatchError: If the uploaded file does not match expected size.
            ObjectNotFoundError: If the destination folder does not exist in SharePoint.
            ProcessingError: If the SharePoint upload or verification fails.

        """
        log.info(
            "Uploading %s bytes to SharePoint destination '%s'.",
            content_size,
            destination,
        )
        self.sharepoint_connector.update_with_file_path(destination)
        self.sharepoint_connector.set_upload_url()
        self.sharepoint_connector.upload_stream_in_chunks(
            BytesIO(content), content_size
        )
        self.sharepoint_connector.verify_uploaded_file(content_size)

    def archive_source_file(
        self, source: str, archive_folder: str, content_size: int
    ) -> None:
        """Archive a file in S3.

        Args:
            source (str): The source S3 key.
            archive_folder (str): The SharePoint folder to move the source file to.
                This must be a folder path, not a file path (i.e., in the same format
                as the source, without the file name and extension).
            content_size (int): The size of the content in bytes.

        Raises:
            NoArchiveFolderGivenError: If archive_folder is not provided when
                source_handling is 'archive' is 'archive'.
            ProcessingError: If the S3 archiving fails.

        """
        archive_key = str(Path(archive_folder) / Path(source).name)
        log.info(
            "Archiving transferred source object from S3: s3://%s/%s -> s3://%s/%s",
            self.bucket.bucket,
            source,
            self.bucket.bucket,
            archive_key,
        )
        self.s3_connector.set_archive_key(archive_key)
        self.s3_connector.archive_object(content_size)

    def delete_source_file(self, source: str) -> None:
        """Delete a file from S3.

        Args:
            source (str): The source S3 key.

        Returns:
            None

        Raises:
            ProcessingError: If the S3 deletion fails.

        """
        log.info(
            "Deleting transferred source object from S3: s3://%s/%s",
            self.bucket.bucket,
            source,
        )
        self.s3_connector.set_key(source)
        self.s3_connector.delete_object()


class UploadToS3Engine(Engine):
    """Engine for uploading files from SharePoint to S3.

    Methods:
        list_source_files: List files available in the SharePoint library.
        download_file: Download a file from the SharePoint library.
        upload_file: Upload a file to the S3 destination.
        delete_source_file: Delete file from SharePoint after successful transfer.
        archive_source_file: Archive file in SharePoint after successful transfer.
        validate_plan: Validate planned file movement is feasible before execution.
        run: Transfer a single file from SharePoint to S3.

    """

    def list_source_files(self) -> list[str]:
        """List all file paths in the SharePoint source library.

        Args:
            None

        Returns:
            list[str]: All object keys in the S3 source bucket.

        Raises:
            ProcessingError: If the listing request fails.

        """
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
            ProcessingError: If one or more validation checks fail.

        """
        log.info(
            "Validating SharePoint->S3 transfer for source '%s' and destination '%s'.",
            source,
            destination,
        )
        errors: list[str] = []

        try:
            self.s3_connector.check_bucket_exists()
        except ProcessingError as exc:
            errors.append(str(exc))

        try:
            self.sharepoint_connector.check_object_exists(source, "file")
        except (IncorrectObjectTypeError, ObjectNotFoundError, ProcessingError) as exc:
            errors.append(str(exc))

        if errors:
            all_errors = "\n".join(f"  - {e}" for e in errors)
            err = f"Validation failed with {len(errors)} error(s):\n {all_errors}"
            raise ProcessingError(err)

        log.info("Validation complete for SharePoint->S3 transfer plan.")

    def download_file(self, source: str) -> bytes:
        """Download a file from SharePoint and return its content as bytes.

        Args:
            source (str): The source path in SharePoint.

        Returns:
            bytes: The content of the SharePoint file as bytes.

        Raises:
            ProcessingError: If the SharePoint download fails.

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
            ProcessingError: If the S3 upload or verification fails.

        """
        log.info(
            "Uploading %s bytes to S3 destination s3://%s/%s.",
            len(content),
            self.bucket.bucket,
            destination,
        )
        self.s3_connector.update_with_key(destination)
        self.s3_connector.upload_to_s3(content)
        self.s3_connector.verify_uploaded_object(expected_size=len(content))

    def delete_source_file(self, source: str) -> None:
        """Delete a file from S3.

        Args:
            source (str): The source S3 key.

        Returns:
            None

        Raises:
            ProcessingError: If the S3 deletion fails.

        """
        log.info("Deleting transferred source file from SharePoint: '%s'", source)
        self.sharepoint_connector.update_with_file_path(source)
        self.sharepoint_connector.delete_file()
