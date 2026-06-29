"""S3 connector for handling interactions with Amazon S3."""

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, ConfigDict, Field

from aws_sharepoint_connector.exceptions import FileSizeMismatchError, ProcessingError
from aws_sharepoint_connector.utils import setup_logger

log = setup_logger()


class S3Connector(BaseModel):
    """Connector for handling interactions with Amazon S3."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    client: Any  # boto3 client; typed as Any because boto3.client is a factory function
    bucket: str
    key: str = Field(default="", init=False)  # set per-file via update_with_key()

    def update_with_key(self, key: str) -> None:
        """Set the S3 object key for the current file operation."""
        self.key = key

    def list_objects(self, prefix: str = "") -> list[str]:
        """List all object keys in the S3 bucket, optionally filtered by prefix.

        Handles pagination automatically; all matching keys are returned regardless
        of bucket size.

        Args:
            prefix (str): Optional key prefix to filter results
                (e.g. ``"reports/2026/"``). Defaults to ``""`` (list all objects).

        Returns:
            list[str]: All object keys in the bucket matching the given prefix.

        Raises:
            ProcessingError: If the listing request fails.

        """
        log.info("Listing objects in s3://%s/%s...", self.bucket, prefix)
        keys: list[str] = []
        kwargs: dict[str, Any] = {"Bucket": self.bucket}
        if prefix:
            kwargs["Prefix"] = prefix
        try:
            while True:
                response = self.client.list_objects_v2(**kwargs)
                keys.extend(obj["Key"] for obj in response.get("Contents", []))
                if not response.get("IsTruncated"):
                    break
                kwargs["ContinuationToken"] = response["NextContinuationToken"]
        except (BotoCoreError, ClientError) as exc:
            err = f"Failed to list objects in s3://{self.bucket}: {exc}"
            raise ProcessingError(err) from exc
        log.info("Found %d object(s) in s3://%s/%s.", len(keys), self.bucket, prefix)
        return keys

    def download_from_s3(self) -> bytes:
        """Download an object from S3 and return its content as bytes.

        Returns:
            bytes: The content of the S3 object as bytes.

        Raises:
            ProcessingError: If the download fails.

        """
        log.info("Downloading object from S3: s3://%s/%s", self.bucket, self.key)
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=self.key)
            return obj["Body"].read()  # type: ignore[no-any-return]
        except (BotoCoreError, ClientError) as exc:
            err = f"Failed to download s3://{self.bucket}/{self.key}: {exc}"
            raise ProcessingError(err) from exc

    def upload_to_s3(self, data: bytes) -> None:
        """Upload data to an S3 bucket.

        Args:
            data (bytes): The data to upload as bytes.

        Returns:
            None

        Raises:
            ProcessingError: If the upload fails.

        """
        log.info(
            "Uploading %s bytes to S3 object s3://%s/%s",
            len(data),
            self.bucket,
            self.key,
        )
        try:
            self.client.put_object(Bucket=self.bucket, Key=self.key, Body=data)
        except (BotoCoreError, ClientError) as exc:
            err = f"Failed to upload object to s3://{self.bucket}/{self.key}: {exc}"
            raise ProcessingError(err) from exc

    def verify_uploaded_object(self, expected_size: int) -> None:
        """Verify object exists in S3 and matches expected byte size.

        Args:
            expected_size (int): The expected size of the uploaded object in bytes.

        Raises:
            FileSizeMismatchError: If the object size does not match the expected size.
            ProcessingError: If the object cannot be retrieved.

        """
        try:
            metadata = self.client.head_object(Bucket=self.bucket, Key=self.key)
        except (BotoCoreError, ClientError) as exc:
            err = (
                "Failed to verify uploaded S3 object "
                f"s3://{self.bucket}/{self.key}: {exc}"
            )
            raise ProcessingError(err) from exc

        actual_size = metadata.get("ContentLength")
        if actual_size != expected_size:
            err = (
                "Verification failed for uploaded S3 object "
                f"s3://{self.bucket}/{self.key}: expected {expected_size} bytes, "
                f"got {actual_size} bytes"
            )
            raise FileSizeMismatchError(err)
        log.info(
            "Verified S3 upload for s3://%s/%s (%s bytes).",
            self.bucket,
            self.key,
            expected_size,
        )

    def check_bucket_exists(self) -> None:
        """Check that the S3 bucket exists and is accessible.

        Raises:
            ProcessingError: If the bucket does not exist or access is denied.

        """
        log.info("Checking access to S3 bucket '%s'.", self.bucket)
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in ("404", "NoSuchBucket"):
                err = f"S3 bucket does not exist: '{self.bucket}'"
            elif code == "403":
                err = (
                    f"Access denied to S3 bucket '{self.bucket}': check IAM permissions"
                )
            else:
                err = f"Failed to access S3 bucket '{self.bucket}': {exc}"
            raise ProcessingError(err) from exc
        except BotoCoreError as exc:
            err = f"Failed to access S3 bucket '{self.bucket}': {exc}"
            raise ProcessingError(err) from exc

    def check_object_exists(self) -> None:
        """Check that the S3 object exists and is accessible.

        Raises:
            ProcessingError: If the object does not exist or access is denied.

        """
        log.info(
            "Checking access to S3 object s3://%s/%s.",
            self.bucket,
            self.key,
        )
        try:
            self.client.head_object(Bucket=self.bucket, Key=self.key)
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in ("404", "NoSuchKey"):
                err = f"S3 object does not exist: s3://{self.bucket}/{self.key}"
            elif code == "403":
                err = (
                    f"Access denied to S3 object s3://{self.bucket}/{self.key}: "
                    "check IAM permissions"
                )
            else:
                err = f"Failed to access S3 object s3://{self.bucket}/{self.key}: {exc}"
            raise ProcessingError(err) from exc
        except BotoCoreError as exc:
            err = f"Failed to access S3 object s3://{self.bucket}/{self.key}: {exc}"
            raise ProcessingError(err) from exc

    def delete_object(self) -> None:
        """Delete the S3 object specified by the current bucket and key.

        Raises:
            ProcessingError: If the delete operation fails.

        """
        log.info("Deleting S3 object s3://%s/%s.", self.bucket, self.key)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=self.key)
        except (BotoCoreError, ClientError) as exc:
            err = f"Failed to delete s3://{self.bucket}/{self.key}: {exc}"
            raise ProcessingError(err) from exc
