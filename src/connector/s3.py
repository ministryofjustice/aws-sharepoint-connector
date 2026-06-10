"""S3 connector for handling interactions with Amazon S3."""

from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, ConfigDict

from connector.exceptions import UploadError


class S3Connector(BaseModel):
    """Connector for handling interactions with Amazon S3."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    client: Any  # boto3 client; typed as Any because boto3.client is a factory function
    bucket: str
    key: str

    def download_from_s3(self) -> bytes:
        """Download an object from S3 and return its content as bytes.

        Args:
            None
        Returns:
            bytes: The content of the S3 object as bytes.

        """
        try:
            obj = self.client.get_object(Bucket=self.bucket, Key=self.key)
            return obj["Body"].read()  # type: ignore[no-any-return]
        except (BotoCoreError, ClientError) as exc:
            err = f"Failed to download s3://{self.bucket}/{self.key}: {exc}"
            raise UploadError(err) from exc

    def upload_to_s3(self, data: bytes) -> None:
        """Upload data to an S3 bucket.

        Args:
            data (bytes): The data to upload as bytes.

        Returns:
            None

        """
        try:
            self.client.put_object(Bucket=self.bucket, Key=self.key, Body=data)
        except (BotoCoreError, ClientError) as exc:
            err = f"Failed to upload object to s3://{self.bucket}/{self.key}: {exc}"
            raise UploadError(err) from exc

    def verify_uploaded_object(self, expected_size: int) -> None:
        """Verify object exists in S3 and matches expected byte size."""
        try:
            metadata = self.client.head_object(Bucket=self.bucket, Key=self.key)
        except (BotoCoreError, ClientError) as exc:
            err = (
                "Failed to verify uploaded S3 object "
                f"s3://{self.bucket}/{self.key}: {exc}"
            )
            raise UploadError(err) from exc

        actual_size = metadata.get("ContentLength")
        if actual_size != expected_size:
            err = (
                "Verification failed for uploaded S3 object "
                f"s3://{self.bucket}/{self.key}: expected {expected_size} bytes, "
                f"got {actual_size} bytes"
            )
            raise UploadError(err)
