"""S3 connector for handling interactions with Amazon S3."""

from dataclasses import dataclass

import boto3


@dataclass
class S3Connector:
    """Connector for handling interactions with Amazon S3."""

    client: boto3.client
    bucket: str
    key: str

    def download_from_s3(self) -> bytes:
        """Download an object from S3 and return its content as bytes.

        Args:
            None
        Returns:
            bytes: The content of the S3 object as bytes.

        """
        obj = self.client.get_object(Bucket=self.bucket, Key=self.key)
        return obj["Body"].read()  # type: ignore[no-any-return]

    def upload_to_s3(self, data: bytes) -> None:
        """Upload data to an S3 bucket.

        Args:
            data (bytes): The data to upload as bytes.

        Returns:
            None

        """
        self.client.put_object(Bucket=self.bucket, Key=self.key, Body=data)
