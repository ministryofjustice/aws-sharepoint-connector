"""Config module.

This file defines the ConnectorConfig class, which loads and validates
all environment-based settings — including
Azure AD credentials, SharePoint settings, and S3 information.

It uses Pydantic's `BaseSettings` to automatically load values from:
  - Environment variables, or
  - A `.env` file in the project root (for local development)
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class S3File(BaseModel):
    """BaseModel for defining an s3 file."""

    source_s3_key: str
    destination_sp_path: str


class S3ToSPMovementPlan(BaseModel):
    """BaseModel for defining a file movement plan from s3 to Sharepoint."""

    bucket: str
    files: list[S3File]


class SharePointFile(BaseModel):
    """BaseModel for defining a SharePoint file."""

    source_sp_path: str
    destination_s3_path: str


class SPToS3MovementPlan(BaseModel):
    """BaseModel for defining a file movement plan from Sharepoint to S3."""

    sp_site: str
    files: list[SharePointFile]


class ConnectorConfig(BaseSettings):
    """Application configuration container.

    Each field corresponds to a setting that can be provided either
    via environment variables or via entries in a `.env` file.
    """

    # These values are used for authenticating with Microsoft Graph.
    SECRET_AZURE_TENANT_ID: UUID
    SECRET_AZURE_CLIENT_ID: SecretStr
    SECRET_AZURE_CLIENT_SECRET: SecretStr

    # Used for identifying where to read from / write to in SharePoint.
    SP_SITE_NAME: str
    SP_LIBRARY_NAME: str
    SP_FOLDER_PATH: str
    SP_FILE_NAME: str

    # The S3 bucket and key to read from / write to.
    S3_BUCKET: str
    FILE_KEY: str

    # upload to S3 or SharePoint
    MODE: Literal["write_to_s3", "write_to_sharepoint"]

    # This tells Pydantic to read values from a .env file by default.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("SP_FOLDER_PATH")
    @classmethod
    def ensure_trailing_slash(cls, v: str) -> str:
        """Ensure the SharePoint folder path ends with a slash.

        Args:
            v (str): The folder path to validate.

        Returns:
            str: The validated folder path, guaranteed to end with a slash.

        """
        return v if v.endswith("/") else f"{v}/"
