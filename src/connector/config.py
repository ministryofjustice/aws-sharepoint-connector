"""Configuration models for the file movement plans and secrets."""

from uuid import UUID

from pydantic import BaseModel, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SharePointFile(BaseModel):
    """BaseModel for defining a SharePoint file.

    Attributes:
        site (str): The source/target Sharepoint site name
        library (str): The source/target document library name
        directory (str | None): The source/target directory within the document library
        filename (str): The source/target file name with extension

    Example:
    `https://justiceuk.sharepoint.com/sites/analytics-site/Documents/exports/reports/2026/04/daily_report.csv`

    - site = analytics-site
    - library = Documents
    - directory = exports/reports/2026/04/
    - filename = daily_report.csv

    """

    site: str
    library: str
    directory: str | None = None
    filename: str

    @field_validator("site")
    @classmethod
    def validate_site(cls, v: str) -> str:
        """Validate that the SharePoint site name is valid.

        - Is a non-empty string
        - Does not include the "https://justiceuk.sharepoint.com/sites/" prefix
        """
        if not v:
            err = "site must be a non-empty string."
            raise ValueError(err)
        if v.startswith("https://justiceuk.sharepoint.com/sites/"):
            err = (
                "site should not include the"
                " 'https://justiceuk.sharepoint.com/sites/' prefix."
            )
            raise ValueError(err)
        return v


class S3File(BaseModel):
    """BaseModel for defining an s3 file.

    Attributes:
        bucket (str): The source/target s3 bucket. Do not include the "s3://" prefix.
        key (str): The source/target s3 key. Must be the complete key including all
            directories, but excluding the bucket and 's3://'prefix

    Example:
    s3://my-bucket/path/to/file1.csv

    - bucket = my-bucket
    - key = path/to/file1.csv

    """

    bucket: str
    key: str

    @field_validator("bucket")
    @classmethod
    def validate_bucket(cls, v: str) -> str:
        """Validate that the bucket name is valid.

        - Is a non-empty string
        - Does not contain the 's3://' prefix
        - Does not end with a slash
        """
        if not v:
            err = "bucket must be a non-empty string."
            raise ValueError(err)
        if v.startswith("s3://"):
            err = "bucket should not include the 's3://' prefix."
            raise ValueError(err)
        if v.endswith("/"):
            err = "bucket name should not end with a slash."
            raise ValueError(err)
        return v

    @field_validator("key")
    @classmethod
    def validate_key(cls, v: str) -> str:
        """Validate that the source s3 key is valid.

        - Is a non-empty string
        - Does not end with a slash (indicating it's a folder, not a file)
        - Does not include the "s3://" prefix

        """
        if not v:
            err = "key must be a non-empty string."
            raise ValueError(err)
        if v.endswith("/"):
            err = "key must point to a file not a folder."
            raise ValueError(err)
        if v.startswith("s3://"):
            err = "key should not include the 's3://bucket-name/' prefix."
            raise ValueError(err)
        return v

    @model_validator(mode="after")
    def validate_bucket_not_in_key(self) -> "S3File":
        """Validate that the bucket name is not included in the key."""
        if self.bucket in self.key:
            err = "key should not include the bucket name."
            raise ValueError(err)
        return self


class S3ToSPMovementPlan(BaseModel):
    """BaseModel for defining a file movement plan from s3 to Sharepoint.

    Attributes:
        source (S3File): An S3File object defining the source file in S3.
        destination (SharePointFile): A SharePointFile object defining the destination
            file in SharePoint.

    """

    source: S3File
    destination: SharePointFile

    @property
    def s3_bucket(self) -> str:
        """Convenience property to access the source S3 bucket."""
        return self.source.bucket

    @property
    def s3_file_key(self) -> str:
        """Convenience property to access the S3 key of the file to move."""
        return self.source.key

    @property
    def sp_library(self) -> str:
        """Convenience property to access the destination SharePoint library."""
        return self.destination.library

    @property
    def sp_site(self) -> str:
        """Convenience property to access the destination SharePoint site."""
        return self.destination.site

    @property
    def sp_directory(self) -> str:
        """Convenience property to access the destination SharePoint directory."""
        return self.destination.directory or ""

    @property
    def sp_file_name(self) -> str:
        """Convenience property to access the destination SharePoint file name."""
        return self.destination.filename


class SPToS3MovementPlan(BaseModel):
    """BaseModel for defining a file movement plan from Sharepoint to S3.

    Attributes:
        source (SharePointFile): A SharePointFile object defining the source file in
            SharePoint.
        destination (S3File): An S3File object defining the destination file in S3.

    """

    source: SharePointFile
    destination: S3File

    @property
    def s3_bucket(self) -> str:
        """Convenience property to access the destination S3 bucket."""
        return self.destination.bucket

    @property
    def s3_file_key(self) -> str:
        """Convenience property to access the S3 key of the file to move."""
        return self.destination.key

    @property
    def sp_library(self) -> str:
        """Convenience property to access the source SharePoint library."""
        return self.source.library

    @property
    def sp_site(self) -> str:
        """Convenience property to access the source SharePoint site."""
        return self.source.site

    @property
    def sp_directory(self) -> str:
        """Convenience property to access the source SharePoint directory."""
        return self.source.directory or ""

    @property
    def sp_file_name(self) -> str:
        """Convenience property to access the source SharePoint file name."""
        return self.source.filename


class DataMovementPlan(BaseModel):
    """BaseModel for defining the overall data movement plan.

    Attributes:
        data_to_move (list[S3ToSPMovementPlan | SPToS3MovementPlan]): A list of file
            movement plans, which can be either from S3 to SharePoint or from
            SharePoint to S3.

    """

    data_to_move: list[S3ToSPMovementPlan | SPToS3MovementPlan]


class SecretConfig(BaseSettings):
    """Application configuration container.

    Each field corresponds to a setting that can be provided either
    via environment variables or via entries in a `.env` file.
    """

    # These values are used for authenticating with Microsoft Graph.
    SECRET_AZURE_TENANT_ID: UUID
    SECRET_AZURE_CLIENT_ID: SecretStr
    SECRET_AZURE_CLIENT_SECRET: SecretStr

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
