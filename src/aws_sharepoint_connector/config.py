"""Configuration models for the connection configurations and secrets."""

from uuid import UUID

from pydantic import BaseModel, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SharePointLibrary(BaseModel):
    """Configuration for a SharePoint document library.

    Attributes:
        domain(str): The SharePoint domain (e.g. ``'organisation.sharepoint.com'``).
        site (str): The source/target SharePoint site name (without the domain).
        library (str): The source/target document library name.

    Example::

        # For a file at:
        # https://organisation.sharepoint.com/sites/analytics-site/Documents/...
        SharePointLibrary(
            domain='organisation.sharepoint.com',
            site='analytics-site',
            library='Documents'
        )

    """

    domain: str
    site: str
    library: str

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        """Validate that the SharePoint domain is valid.

        - Is a non-empty string
        """
        if not v:
            err = "domain, site, and library must be non-empty strings."
            raise ValueError(err)
        return v

    @field_validator("site", "library")
    @classmethod
    def validate_site(cls, v: str) -> str:
        """Validate that the SharePoint site name is valid.

        - Is a non-empty string
        """
        if not v:
            err = "domain, site, and library must be non-empty strings."
            raise ValueError(err)
        return v


class S3Bucket(BaseModel):
    """Configuration for an S3 bucket.

    Attributes:
        bucket (str): The source/target S3 bucket name. Do not include the
            ``s3://`` prefix or a trailing slash.

    Example::

        # For s3://my-bucket/path/to/file1.csv
        S3Bucket(bucket='my-bucket')

    """

    bucket: str

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
