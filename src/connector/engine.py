"""Engine module for handling file transfers between S3 and SharePoint."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Any

import boto3

from connector.config import (
    MovementPlan,
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
    s3_client: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Post-initialization to create S3 and SharePoint connectors."""
        log.info("Setting up storage connectors...")
        self.s3_client = boto3.client("s3")
        self.sharepoint_connector = SharePointConnector(
            secrets=self.secrets, library=self.library
        )

    @abstractmethod
    def download_file(self, source: str) -> bytes:
        """Download a file from the source storage."""

    @abstractmethod
    def upload_file(self, content: bytes, destination: str) -> None:
        """Upload a file to the destination storage."""

    @abstractmethod
    def validate_plans(self, plans: list[MovementPlan]) -> None:
        """Pre-flight check all movement plans before execution.

        Must check every plan and collect all errors before raising, so the
        caller receives a single report of every problem rather than discovering
        failures one at a time.

        Args:
            plans (list[MovementPlan]): The movement plans to validate.

        Raises:
            UploadError: If one or more validation checks fail.

        """

    def run(self, source: str, destination: str) -> None:
        """Transfer a single file from source to destination storage.

        Args:
            source (str): Source file path (S3 key or SharePoint path).
            destination (str): Destination file path (SharePoint path or S3 key).

        Raises:
            UploadError: If the download or upload step fails.

        """
        log.info("Starting transfer: '%s' -> '%s'", source, destination)
        content = self.download_file(source)
        self.upload_file(content, destination)
        log.info(
            "Transfer complete: '%s' -> '%s' (%s bytes)",
            source,
            destination,
            len(content),
        )


class UploadToSharePointEngine(Engine):
    """Engine for uploading files from S3 to SharePoint."""

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
        s3_connector = S3Connector(
            client=self.s3_client,
            bucket=self.bucket.bucket,
            key=source,
        )
        return s3_connector.download_from_s3()

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

    def validate_plans(self, plans: list[MovementPlan]) -> None:
        """Pre-flight check all plans before execution.

        Validates that:

        - The S3 source bucket is accessible.
        - Each source S3 key exists.
        - Each destination SharePoint parent folder exists.

        All errors are collected before raising, so the caller receives a single
        report of every problem.

        Args:
            plans (list[MovementPlan]): The movement plans to validate.

        Raises:
            UploadError: If one or more validation checks fail.

        """
        log.info("Running pre-flight validation for %d plan(s)...", len(plans))
        errors: list[str] = []

        try:
            S3Connector(
                client=self.s3_client, bucket=self.bucket.bucket, key=""
            ).check_bucket_exists()
        except UploadError as exc:
            errors.append(str(exc))

        for plan in plans:
            try:
                S3Connector(
                    client=self.s3_client,
                    bucket=self.bucket.bucket,
                    key=plan.source,
                ).check_object_exists()
            except UploadError as exc:
                errors.append(str(exc))

            folder = str(Path(plan.destination).parent)
            if folder and folder != ".":
                try:
                    self.sharepoint_connector.check_folder_exists(folder)
                except UploadError as exc:
                    errors.append(str(exc))

        if errors:
            all_errors = "\n".join(f"  - {e}" for e in errors)
            err = (
                f"Pre-flight validation failed with {len(errors)} error(s):\n"
                f"{all_errors}"
            )
            raise UploadError(err)

        log.info("Pre-flight validation passed for all %d plan(s).", len(plans))


class UploadToS3Engine(Engine):
    """Engine for uploading files from SharePoint to S3."""

    def download_file(self, source: str) -> bytes:
        """Download a file from SharePoint and return its content as bytes.

        Args:
            source (str): The source path in SharePoint.

        Returns:
            bytes: The content of the SharePoint file as bytes.

        Raises:
            UploadError: If the SharePoint download fails.

        """
        try:
            log.info(
                "Downloading '%s' from SharePoint library '%s'...",
                source,
                self.library.library,
            )
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
        s3_connector = S3Connector(
            client=self.s3_client,
            bucket=self.bucket.bucket,
            key=destination,
        )
        s3_connector.upload_to_s3(content)
        s3_connector.verify_uploaded_object(expected_size=len(content))
        log.info("S3 upload verification succeeded.")

    def validate_plans(self, plans: list[MovementPlan]) -> None:
        """Pre-flight check all plans before execution.

        Validates that:

        - The S3 destination bucket is accessible.
        - Each source file exists in SharePoint.

        All errors are collected before raising, so the caller receives a single
        report of every problem.

        Args:
            plans (list[MovementPlan]): The movement plans to validate.

        Raises:
            UploadError: If one or more validation checks fail.

        """
        log.info("Running pre-flight validation for %d plan(s)...", len(plans))
        errors: list[str] = []

        try:
            S3Connector(
                client=self.s3_client, bucket=self.bucket.bucket, key=""
            ).check_bucket_exists()
        except UploadError as exc:
            errors.append(str(exc))

        for plan in plans:
            try:
                self.sharepoint_connector.check_file_exists(plan.source)
            except UploadError as exc:
                errors.append(str(exc))

        if errors:
            all_errors = "\n".join(f"  - {e}" for e in errors)
            err = (
                f"Pre-flight validation failed with {len(errors)} error(s):\n"
                f"{all_errors}"
            )
            raise UploadError(err)

        log.info("Pre-flight validation passed for all %d plan(s).", len(plans))
