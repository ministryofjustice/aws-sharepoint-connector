"""Unit tests for create_engine() and create_movement_plan() in main.py."""

from collections.abc import Generator
from unittest.mock import patch

import pytest

from connector import engine as engine_module
from connector.config import MovementPlan, SecretConfig
from connector.main import create_engine, create_movement_plan


@pytest.fixture(autouse=True)
def suppress_engine_init() -> Generator[None]:
    """Prevent Engine.__post_init__ from making real API calls in all tests."""
    with patch("connector.engine.Engine.__post_init__"):
        yield


class TestCreateEngine:
    """Tests for the create_engine() factory function."""

    def test_write_to_s3_returns_upload_to_s3_engine(self) -> None:
        """Test that write_to_s3 mode returns an UploadToS3Engine."""
        eng = create_engine("write_to_s3", "analytics-site", "Documents", "my-bucket")
        assert isinstance(eng, engine_module.UploadToS3Engine)

    def test_write_to_sharepoint_returns_upload_to_sharepoint_engine(self) -> None:
        """Test that write_to_sharepoint mode returns an UploadToSharePointEngine."""
        eng = create_engine(
            "write_to_sharepoint", "analytics-site", "Documents", "my-bucket"
        )
        assert isinstance(eng, engine_module.UploadToSharePointEngine)

    def test_engine_has_correct_secrets(self) -> None:
        """Test that the engine is initialised with a valid SecretConfig."""
        eng = create_engine("write_to_s3", "analytics-site", "Documents", "my-bucket")
        assert isinstance(eng.secrets, SecretConfig)

    def test_engine_has_correct_library_site(self) -> None:
        """Test that the engine library carries the provided site slug."""
        eng = create_engine("write_to_s3", "my-site", "Documents", "my-bucket")
        assert eng.library.site == "my-site"

    def test_engine_has_correct_library_name(self) -> None:
        """Test that the engine library carries the provided library name."""
        eng = create_engine("write_to_s3", "analytics-site", "MyLibrary", "my-bucket")
        assert eng.library.library == "MyLibrary"

    def test_engine_has_correct_bucket(self) -> None:
        """Test that the engine bucket carries the provided bucket name."""
        eng = create_engine(
            "write_to_s3", "analytics-site", "Documents", "target-bucket"
        )
        assert eng.bucket.bucket == "target-bucket"

    def test_invalid_mode_raises_value_error(self) -> None:
        """Test that an unrecognised mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid mode"):
            create_engine(
                "invalid_mode",  # type: ignore[arg-type]
                "analytics-site",
                "Documents",
                "my-bucket",
            )


class TestCreateMovementPlan:
    """Tests for the create_movement_plan() helper."""

    def test_returns_list_of_movement_plans(self) -> None:
        """Test that the returned list contains MovementPlan instances."""
        plans = create_movement_plan(
            [
                {
                    "source": "reports/2026/file1.csv",
                    "destination": "path/to/file1.csv",
                },
                {
                    "source": "reports/2026/file2.csv",
                    "destination": "path/to/file2.csv",
                },
            ]
        )
        assert len(plans) == 2
        assert all(isinstance(p, MovementPlan) for p in plans)

    def test_plans_have_correct_source_and_destination(self) -> None:
        """Test that source and destination strings are preserved exactly."""
        plans = create_movement_plan(
            [{"source": "sp/path/file.csv", "destination": "s3/path/file.csv"}]
        )
        assert plans[0].source == "sp/path/file.csv"
        assert plans[0].destination == "s3/path/file.csv"

    def test_empty_plan_list_returns_empty_list(self) -> None:
        """Test that an empty input produces an empty list."""
        assert create_movement_plan([]) == []

    def test_single_plan_returns_single_element_list(self) -> None:
        """Test that a single-item input produces a one-element list."""
        plans = create_movement_plan(
            [{"source": "file.csv", "destination": "dest/file.csv"}]
        )
        assert len(plans) == 1


class TestEngineRunWorkflow:
    """Integration tests for the create_engine → engine.run() usage pattern."""

    def test_run_passes_download_result_to_upload(self) -> None:
        """Test that bytes returned by download_file are forwarded to upload_file."""
        fake_content = b"file-content"

        with (
            patch(
                "connector.engine.UploadToS3Engine.download_file",
                autospec=True,
                return_value=fake_content,
            ) as mock_dl,
            patch(
                "connector.engine.UploadToS3Engine.upload_file",
                autospec=True,
            ) as mock_ul,
        ):
            eng = create_engine(
                "write_to_s3", "analytics-site", "Documents", "my-bucket"
            )
            eng.run("reports/file.csv", "path/to/file.csv")

        mock_dl.assert_called_once_with(eng, "reports/file.csv")
        mock_ul.assert_called_once_with(eng, fake_content, "path/to/file.csv")

    def test_s3_engine_used_for_write_to_s3_mode(self) -> None:
        """Test that the UploadToS3Engine is selected for write_to_s3 mode."""
        with (
            patch(
                "connector.engine.UploadToS3Engine.download_file",
                autospec=True,
                return_value=b"data",
            ),
            patch("connector.engine.UploadToS3Engine.upload_file", autospec=True),
            patch(
                "connector.engine.UploadToSharePointEngine.download_file",
                autospec=True,
            ) as sp_dl,
            patch(
                "connector.engine.UploadToSharePointEngine.upload_file",
                autospec=True,
            ) as sp_ul,
        ):
            eng = create_engine(
                "write_to_s3", "analytics-site", "Documents", "my-bucket"
            )
            eng.run("reports/file.csv", "path/to/file.csv")

        sp_dl.assert_not_called()
        sp_ul.assert_not_called()

    def test_sharepoint_engine_used_for_write_to_sharepoint_mode(self) -> None:
        """Test that UploadToSharePointEngine is selected for write_to_sharepoint."""
        with (
            patch(
                "connector.engine.UploadToSharePointEngine.download_file",
                autospec=True,
                return_value=b"data",
            ),
            patch(
                "connector.engine.UploadToSharePointEngine.upload_file",
                autospec=True,
            ),
            patch(
                "connector.engine.UploadToS3Engine.download_file", autospec=True
            ) as s3_dl,
            patch(
                "connector.engine.UploadToS3Engine.upload_file", autospec=True
            ) as s3_ul,
        ):
            eng = create_engine(
                "write_to_sharepoint", "analytics-site", "Documents", "my-bucket"
            )
            eng.run("path/to/file.csv", "reports/file.csv")

        s3_dl.assert_not_called()
        s3_ul.assert_not_called()
