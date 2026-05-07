"""Configuration models for the file movement plans and secrets."""

from uuid import UUID

from pydantic import BaseModel, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class S3File(BaseModel):
    """BaseModel for defining an s3 file.

    Attributes:
    source_s3_key (str): The key of the source file in s3. Must be the complete
    key including any "folders" (e.g. "path/to/file.csv"), and must not include
    the "s3://bucket-name/" prefix.

    destination_sp_path (str): The path in SharePoint to write the file to. This can be
    the full path, or truncated to start from the Sharepoint library
    (e.g. "Shared Documents/Folder1/file.csv") - i.e., exclude 'https://justiceuk.sharepoint.com/sites/'.
    Must contain the site name, library name and then any subfolders.
    Must end with the file name and file extension.

    """

    source_s3_key: str
    destination_sp_path: str

    @field_validator("source_s3_key")
    @classmethod
    def validate_source_s3_key(cls, v: str) -> str:
        """Validate that the source s3 key is valid.

        - Is a non-empty string
        - Does not end with a slash (indicating it's a folder, not a file)
        - Does not include the "s3://" prefix

        """
        if not v:
            err = "source_s3_key must be a non-empty string."
            raise ValueError(err)
        if v.endswith("/"):
            err = "source_s3_key must point to a file not a folder."
            raise ValueError(err)
        if v.startswith("s3://"):
            err = "source_s3_key should not include the 's3://bucket-name/' prefix."
            raise ValueError(err)
        return v

    @field_validator("destination_sp_path")
    @classmethod
    def validate_destination_sp_path(cls, v: str) -> str:
        """Validate that the destination SharePoint path is valid.

        - Is a non-empty string
        - Contains at least two slashes (providing the site and library names)
        - Ends with a file name and extension

        Removes the base Sharepoint URL and '/sites/' if included
        """
        if not v:
            err = "destination_sp_path must be a non-empty string."
            raise ValueError(err)
        if "sites/" in v:
            v = v.split("sites/", maxsplit=1)[-1]
        if v.count("/") < 2:  # noqa: PLR2004
            err = (
                "destination_sp_path must include at least two slashes (e.g."
                " 'site-name/library-name/file.csv')."
            )
            raise ValueError(err)
        if v.split("/", maxsplit=-1)[-1].count(".") != 1:
            err = (
                "destination_sp_path must end with a file name and extension"
                " (e.g. 'file.csv')."
            )
            raise ValueError(err)
        return v


class S3ToSPMovementPlan(BaseModel):
    """BaseModel for defining a file movement plan from s3 to Sharepoint.

    Attributes:
        bucket (str): The name of the S3 bucket to read from. Must not include
        the 's3://' prefix.
        files (list[S3File]): A list of S3File objects defining the files to be moved
        and their destination paths in SharePoint.

    """

    bucket: str
    files: list[S3File]

    @field_validator("bucket")
    @classmethod
    def validate_bucket(cls, v: str) -> str:
        """Validate that the bucket name is valid.

        - Is not an empty string
        - Does not contain the 's3://' prefix
        """
        if not v:
            err = "bucket must be a non-empty string."
            raise ValueError(err)
        if v.startswith("s3://"):
            err = "bucket should not include the 's3://' prefix."
            raise ValueError(err)
        return v


class SharePointFile(BaseModel):
    """BaseModel for defining a SharePoint file.

    Attributes:
        source_sp_path (str): The path of the source file in SharePoint. Must be the
        complete folder path (excluding the Sharepoint site name) without the
        "https://justiceuk.sharepoint.com/sites/" prefix. If the file is located at
        "https://justiceuk.sharepoint.com/sites/analytics-site/Shared%20Documents/
        reports/2026/daily_report.csv", the source_sp_path should be
        "Shared Documents/reports/2026/daily_report.csv"

        destination_s3_path (str): The complete s3 path to write the file to, including
        the 's3://' prefix and the bucket name (e.g. "s3://bucket-name/path/to/file.csv").

    """

    source_sp_path: str
    destination_s3_path: str

    @field_validator("source_sp_path")
    @classmethod
    def validate_source_sp_path(cls, v: str) -> str:
        """Validate that the source SharePoint path is valid.

        - Is a non-empty string
        - Contains at least one slash (providing the library name)
        - Ends with a file name and extension
        - Does not include the "https://justiceuk.sharepoint.com/sites/" prefix

        """
        if not v:
            err = "source_sp_path must be a non-empty string."
            raise ValueError(err)
        if v.startswith("https://justiceuk.sharepoint.com/sites/"):
            err = (
                "source_sp_path should not include the"
                " 'https://justiceuk.sharepoint.com/sites/' prefix."
            )
            raise ValueError(err)
        if v.count("/") < 1:
            err = (
                "source_sp_path must include at least one slash (e.g."
                " 'library-name/file.csv')."
            )
            raise ValueError(err)
        if v.split("/", maxsplit=-1)[-1].count(".") != 1:
            err = (
                "source_sp_path must end with a file name and extension"
                " (e.g. 'file.csv')."
            )
            raise ValueError(err)
        return v


class SPToS3MovementPlan(BaseModel):
    """BaseModel for defining a file movement plan from Sharepoint to S3.

    Attributes:
        sp_site (str): The name of the SharePoint site. This should just be the single
        string name of the site (e.g. "analytics-site"), not the full URL.
        files (list[SharePointFile]): A list of SharePointFile objects defining the
        files to be moved and their destination paths in S3.

    """

    sp_site: str
    files: list[SharePointFile]

    @field_validator("sp_site")
    @classmethod
    def validate_sp_site(cls, v: str) -> str:
        """Validate that the SharePoint site name is valid.

        - Is a non-empty string
        - Does not include the "https://justiceuk.sharepoint.com/sites/" prefix
        """
        if not v:
            err = "sp_site must be a non-empty string."
            raise ValueError(err)
        if v.startswith("https://justiceuk.sharepoint.com/sites/"):
            err = (
                "sp_site should not include the"
                " 'https://justiceuk.sharepoint.com/sites/' prefix."
            )
            raise ValueError(err)
        return v


class ConnectorConfig(BaseSettings):
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
