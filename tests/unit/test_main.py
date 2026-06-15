"""Unit tests for create_engine() in main.py."""

from collections.abc import Generator
from unittest.mock import patch

import pytest

from connector import engine as engine_module
from connector.main import create_engine


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

    def test_invalid_mode_raises_value_error(self) -> None:
        """Test that an unrecognised mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid mode"):
            create_engine(
                "invalid_mode",  # type: ignore[arg-type]
                "analytics-site",
                "Documents",
                "my-bucket",
            )
