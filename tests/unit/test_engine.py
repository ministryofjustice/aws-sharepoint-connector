"""Unit tests for the engine module."""

from unittest.mock import patch

import boto3
import pytest

from connector import engine
from connector.config import MovementPlan, SecretConfig
from connector.exceptions import UploadError
from connector.s3 import S3Connector
from connector.sharepoint import SharePointConnector
from tests import test_utils as utils

SP_FILE_PATH = utils.SP_FILE_PATH
SP_FILE_NAME = utils.SP_FILE_NAME
S3_KEY = utils.S3_KEY
S3_BUCKET_NAME = utils.S3_BUCKET
DEST_S3_BUCKET = "my-destination-bucket"


class TestEngines:
    """Unit tests for the UploadToSharePointEngine and UploadToS3Engine classes."""

    def setup_engine(
        self, engine_to_use: str, s3: boto3.client
    ) -> engine.UploadToSharePointEngine | engine.UploadToS3Engine:
        """Set up the engine for testing."""
        if engine_to_use == "sharepoint":
            with utils.sharepoint_connector_patches():
                return engine.UploadToSharePointEngine(
                    secrets=SecretConfig(),  # type: ignore[call-arg]
                    library=utils.make_sharepoint_library(),
                    bucket=utils.make_s3_bucket(),
                )
        if engine_to_use == "s3":
            with utils.sharepoint_connector_patches():
                return engine.UploadToS3Engine(
                    secrets=SecretConfig(),  # type: ignore[call-arg]
                    library=utils.make_sharepoint_library(),
                    bucket=utils.make_s3_bucket(),
                )
        err = "Invalid engine type specified: expected 'sharepoint' or 's3'"
        raise ValueError(err)

    def test_upload_sharepoint_list_source_files(self, s3: boto3.client) -> None:
        """list_source_files returns all S3 object keys from the source bucket."""
        with patch.object(
            S3Connector, "list_objects", return_value=["file1.csv", "file2.csv"]
        ) as mock_list:
            upload_sp_engine = self.setup_engine("sharepoint", s3)
            files = upload_sp_engine.list_source_files()

        assert files == ["file1.csv", "file2.csv"]
        mock_list.assert_called_once_with()

    def test_upload_sharepoint_download_file(self, s3: boto3.client) -> None:
        """Test that download_file fetches the correct bytes from S3."""
        with (
            patch.object(
                S3Connector, "download_from_s3", return_value=b"file content"
            ) as mock_download,
            patch.object(S3Connector, "update_with_key") as mock_update_key,
        ):
            upload_sp_engine = self.setup_engine("sharepoint", s3)
            data = upload_sp_engine.download_file(S3_KEY)

        assert data == b"file content"
        mock_update_key.assert_called_once_with(S3_KEY)
        mock_download.assert_called_once_with()

    def test_upload_sharepoint_upload_file(self, s3: boto3.client) -> None:
        """Test that upload_file calls the correct SharePoint methods."""
        with (
            patch.object(
                SharePointConnector, "update_with_file_path"
            ) as mock_update_path,
            patch.object(SharePointConnector, "set_upload_url") as mock_set_upload_url,
            patch.object(
                SharePointConnector, "upload_stream_in_chunks"
            ) as mock_upload_stream,
            patch.object(
                SharePointConnector, "verify_uploaded_file"
            ) as mock_verify_upload,
        ):
            upload_sp_engine = self.setup_engine("sharepoint", s3)
            upload_sp_engine.upload_file(b"Test content", SP_FILE_PATH)

        mock_update_path.assert_called_once_with(SP_FILE_PATH)
        mock_set_upload_url.assert_called_once_with()
        assert mock_upload_stream.call_count == 1
        assert mock_upload_stream.call_args[0][0].getvalue() == b"Test content"
        assert mock_upload_stream.call_args[0][1] == len(b"Test content")
        mock_verify_upload.assert_called_once_with(expected_size=len(b"Test content"))

    def test_upload_sharepoint_delete_source_file(self, s3: boto3.client) -> None:
        """Test that delete_source_file calls the correct S3 method."""
        with (
            patch.object(S3Connector, "update_with_key") as mock_update_key,
            patch.object(S3Connector, "delete_object") as mock_delete_object,
        ):
            upload_sp_engine = self.setup_engine("sharepoint", s3)
            upload_sp_engine.delete_source_file(S3_KEY)

        mock_update_key.assert_called_once_with(S3_KEY)
        mock_delete_object.assert_called_once_with()

    def test_upload_sharepoint_validate_plans_valid(self, s3: boto3.client) -> None:
        """Test that validate_plans returns True for valid plans."""
        valid_plan = MovementPlan(
            source="reports/2026/file.csv", destination="path/to/file.csv"
        )
        upload_sp_engine = self.setup_engine("sharepoint", s3)

        with (
            patch.object(S3Connector, "check_bucket_exists"),
            patch.object(S3Connector, "update_with_key"),
            patch.object(S3Connector, "check_object_exists"),
            patch.object(SharePointConnector, "check_object_exists"),
        ):
            upload_sp_engine.validate_plans([valid_plan])
        assert True  #  No exceptions raised

    @pytest.mark.parametrize(
        ("object_to_fail", "method_to_fail"),
        [
            (S3Connector, "check_bucket_exists"),
            (S3Connector, "update_with_key"),
            (S3Connector, "check_object_exists"),
            (SharePointConnector, "check_object_exists"),
        ],
    )
    def test_upload_sharepoint_validate_plans_invalid(
        self,
        object_to_fail: type[SharePointConnector | S3Connector],
        method_to_fail: str,
        s3: boto3.client,
    ) -> None:
        """Test that validate_plans raises UploadError for invalid plans."""
        invalid_plan = MovementPlan(
            source="reports/2026/file.csv", destination="path/to/file.csv"
        )
        upload_sp_engine = self.setup_engine("sharepoint", s3)

        with (
            patch.object(S3Connector, "check_bucket_exists"),
            patch.object(S3Connector, "update_with_key"),
            patch.object(S3Connector, "check_object_exists"),
            patch.object(SharePointConnector, "check_object_exists"),
            patch.object(
                object_to_fail,
                method_to_fail,
                side_effect=UploadError("Validation failed"),
            ),
            pytest.raises(UploadError) as exc_info,
        ):
            upload_sp_engine.validate_plans([invalid_plan])

        assert "Validation failed" in str(exc_info.value)
        assert "Pre-flight validation failed with 1 error(s)" in str(exc_info.value)

    def test_upload_sharepoint_validation_plans_multi_invalid(
        self, s3: boto3.client
    ) -> None:
        """Test that validate_plans raises UploadError for multiple invalid plans."""
        invalid_plan = MovementPlan(
            source="reports/2026/file.csv", destination="path/to/file.csv"
        )
        upload_sp_engine = self.setup_engine("sharepoint", s3)

        with (
            patch.object(
                S3Connector,
                "check_bucket_exists",
                side_effect=UploadError("S3 validation failed"),
            ),
            patch.object(
                SharePointConnector,
                "check_object_exists",
                side_effect=UploadError("SharePoint validation failed"),
            ),
            patch.object(S3Connector, "update_with_key"),
            patch.object(S3Connector, "check_object_exists"),
            pytest.raises(UploadError) as exc_info,
        ):
            upload_sp_engine.validate_plans([invalid_plan])

        assert "S3 validation failed" in str(exc_info.value)
        assert "SharePoint validation failed" in str(exc_info.value)
        assert "Pre-flight validation failed with 2 error(s)" in str(exc_info.value)

    @pytest.mark.parametrize(
        ("exp_delete_calls", "delete"),
        [
            (1, True),
            (0, False),
        ],
    )
    def test_upload_sharepoint_run_delete_option(
        self, exp_delete_calls: int, *, delete: bool, s3: boto3.client
    ) -> None:
        """Test that run executes the upload process without errors."""
        plan = MovementPlan(
            source="reports/2026/file.csv", destination="path/to/file.csv"
        )
        with (
            patch.object(
                engine.UploadToSharePointEngine,
                "download_file",
                return_value=b"file content",
            ) as mock_download,
            patch.object(
                engine.UploadToSharePointEngine, "upload_file"
            ) as mock_upload_file,
            patch.object(
                engine.UploadToSharePointEngine, "delete_source_file"
            ) as mock_delete_object,
        ):
            upload_sp_engine = self.setup_engine("sharepoint", s3)
            upload_sp_engine.run(plan.source, plan.destination, delete=delete)

        mock_download.assert_called_once_with("reports/2026/file.csv")
        mock_upload_file.assert_called_once_with(b"file content", "path/to/file.csv")
        assert mock_delete_object.call_count == exp_delete_calls

    def test_upload_sharepoint_run_no_delete_option(self, s3: boto3.client) -> None:
        """Test that run executes the upload process without errors."""
        plan = MovementPlan(
            source="reports/2026/file.csv", destination="path/to/file.csv"
        )
        with (
            patch.object(
                engine.UploadToSharePointEngine,
                "download_file",
                return_value=b"file content",
            ) as mock_download,
            patch.object(
                engine.UploadToSharePointEngine, "upload_file"
            ) as mock_upload_file,
            patch.object(
                engine.UploadToSharePointEngine, "delete_source_file"
            ) as mock_delete_object,
        ):
            upload_sharepoint_engine = self.setup_engine("sharepoint", s3)
            upload_sharepoint_engine.run(plan.source, plan.destination)

        mock_download.assert_called_once_with("reports/2026/file.csv")
        mock_upload_file.assert_called_once_with(b"file content", "path/to/file.csv")
        assert mock_delete_object.call_count == 0

    def test_upload_s3_list_source_files(self, s3: boto3.client) -> None:
        """list_source_files returns all S3 object keys from the source bucket."""
        with patch.object(
            SharePointConnector, "list_files", return_value=["file1.csv", "file2.csv"]
        ) as mock_list:
            upload_s3_engine = self.setup_engine("s3", s3)
            files = upload_s3_engine.list_source_files()

        assert files == ["file1.csv", "file2.csv"]
        mock_list.assert_called_once_with()

    def test_upload_s3_download_file(self, s3: boto3.client) -> None:
        """Test that download_file fetches the correct bytes from SharePoint."""
        with (
            patch.object(
                SharePointConnector, "update_with_file_path"
            ) as mock_update_filepath,
            patch.object(SharePointConnector, "set_download_url") as mock_download_url,
            patch.object(
                SharePointConnector, "fetch_file", return_value=b"file content"
            ) as mock_fetch_file,
        ):
            upload_s3_engine = self.setup_engine("s3", s3)
            data = upload_s3_engine.download_file(SP_FILE_PATH)

        assert data == b"file content"
        mock_update_filepath.assert_called_once_with(SP_FILE_PATH)
        mock_download_url.assert_called_once_with()
        mock_fetch_file.assert_called_once_with()

    def test_upload_s3_upload_file(self, s3: boto3.client) -> None:
        """Test that upload_file calls the correct S3 methods."""
        with (
            patch.object(S3Connector, "update_with_key") as mock_update_key,
            patch.object(S3Connector, "upload_to_s3") as mock_upload_to_s3,
            patch.object(S3Connector, "verify_uploaded_object") as mock_verify_upload,
        ):
            upload_s3_engine = self.setup_engine("s3", s3)
            upload_s3_engine.upload_file(b"Test content", SP_FILE_PATH)

        mock_update_key.assert_called_once_with(SP_FILE_PATH)
        mock_upload_to_s3.assert_called_once_with(b"Test content")
        mock_verify_upload.assert_called_once_with(expected_size=len(b"Test content"))

    def test_upload_s3_delete_source_file(self, s3: boto3.client) -> None:
        """Test that delete_source_file calls the correct SharePoint method."""
        with (
            patch.object(
                SharePointConnector, "update_with_file_path"
            ) as mock_update_filepath,
            patch.object(SharePointConnector, "delete_file") as mock_delete_object,
        ):
            upload_s3_engine = self.setup_engine("s3", s3)
            upload_s3_engine.delete_source_file(SP_FILE_PATH)

        mock_update_filepath.assert_called_once_with(SP_FILE_PATH)
        mock_delete_object.assert_called_once_with()

    def test_upload_s3_validate_plans_valid(self, s3: boto3.client) -> None:
        """Test that validate_plans returns True for valid plans."""
        valid_plan = MovementPlan(
            source="reports/2026/file.csv", destination="path/to/file.csv"
        )
        upload_s3_engine = self.setup_engine("s3", s3)

        with (
            patch.object(S3Connector, "check_bucket_exists"),
            patch.object(SharePointConnector, "check_object_exists"),
        ):
            upload_s3_engine.validate_plans([valid_plan])
        assert True  #  No exceptions raised

    @pytest.mark.parametrize(
        ("object_to_fail", "method_to_fail"),
        [
            (S3Connector, "check_bucket_exists"),
            (SharePointConnector, "check_object_exists"),
        ],
    )
    def test_upload_s3_validate_plans_invalid(
        self,
        object_to_fail: type[SharePointConnector | S3Connector],
        method_to_fail: str,
        s3: boto3.client,
    ) -> None:
        """Test that validate_plans raises UploadError for invalid plans."""
        invalid_plan = MovementPlan(
            source="reports/2026/file.csv", destination="path/to/file.csv"
        )
        upload_s3_engine = self.setup_engine("s3", s3)

        with (
            patch.object(S3Connector, "check_bucket_exists"),
            patch.object(SharePointConnector, "check_object_exists"),
            patch.object(
                object_to_fail,
                method_to_fail,
                side_effect=UploadError("Validation failed"),
            ),
            pytest.raises(UploadError) as exc_info,
        ):
            upload_s3_engine.validate_plans([invalid_plan])

        assert "Validation failed" in str(exc_info.value)
        assert "Pre-flight validation failed with 1 error(s)" in str(exc_info.value)

    def test_upload_s3_validation_plans_multi_invalid(self, s3: boto3.client) -> None:
        """Test that validate_plans raises UploadError for multiple invalid plans."""
        invalid_plan = MovementPlan(
            source="reports/2026/file.csv", destination="path/to/file.csv"
        )
        upload_s3_engine = self.setup_engine("s3", s3)

        with (
            patch.object(
                S3Connector,
                "check_bucket_exists",
                side_effect=UploadError("S3 validation failed"),
            ),
            patch.object(
                SharePointConnector,
                "check_object_exists",
                side_effect=UploadError("SharePoint validation failed"),
            ),
            pytest.raises(UploadError) as exc_info,
        ):
            upload_s3_engine.validate_plans([invalid_plan])

        assert "S3 validation failed" in str(exc_info.value)
        assert "SharePoint validation failed" in str(exc_info.value)
        assert "Pre-flight validation failed with 2 error(s)" in str(exc_info.value)

    @pytest.mark.parametrize(
        ("exp_delete_calls", "delete"),
        [
            (1, True),
            (0, False),
        ],
    )
    def test_upload_s3_run_delete_option(
        self, exp_delete_calls: int, *, delete: bool, s3: boto3.client
    ) -> None:
        """Test that run executes the upload process without errors."""
        plan = MovementPlan(
            source="reports/2026/file.csv", destination="path/to/file.csv"
        )
        with (
            patch.object(
                engine.UploadToS3Engine,
                "download_file",
                return_value=b"file content",
            ) as mock_download,
            patch.object(engine.UploadToS3Engine, "upload_file") as mock_upload_file,
            patch.object(
                engine.UploadToS3Engine, "delete_source_file"
            ) as mock_delete_object,
        ):
            upload_s3_engine = self.setup_engine("s3", s3)
            upload_s3_engine.run(plan.source, plan.destination, delete=delete)

        mock_download.assert_called_once_with("reports/2026/file.csv")
        mock_upload_file.assert_called_once_with(b"file content", "path/to/file.csv")
        assert mock_delete_object.call_count == exp_delete_calls

    def test_upload_s3_run_no_delete_option(self, s3: boto3.client) -> None:
        """Test that run executes the upload process without errors."""
        plan = MovementPlan(
            source="reports/2026/file.csv", destination="path/to/file.csv"
        )
        with (
            patch.object(
                engine.UploadToS3Engine,
                "download_file",
                return_value=b"file content",
            ) as mock_download,
            patch.object(engine.UploadToS3Engine, "upload_file") as mock_upload_file,
            patch.object(
                engine.UploadToS3Engine, "delete_source_file"
            ) as mock_delete_object,
        ):
            upload_s3_engine = self.setup_engine("s3", s3)
            upload_s3_engine.run(plan.source, plan.destination)

        mock_download.assert_called_once_with("reports/2026/file.csv")
        mock_upload_file.assert_called_once_with(b"file content", "path/to/file.csv")
        assert mock_delete_object.call_count == 0
