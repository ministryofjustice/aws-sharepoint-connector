"""Unit tests for the run() function of the connector application."""

import json
from collections.abc import Generator
from contextlib import contextmanager
from unittest.mock import Mock, patch

import pytest

from connector import engine as engine_module
from connector.config import SecretConfig
from connector.exceptions import UploadError
from connector.main import run
from tests.test_utils import (
    create_s3_to_sp_movement_plan,
    create_sp_to_s3_movement_plan,
)


@contextmanager  # pylint: disable=too-many-arguments
def mock_all_engines(  # noqa: PLR0913
    s3_dl_return: bytes | None = b"data",
    s3_dl_side_effect: Exception | None = None,
    s3_ul_side_effect: Exception | None = None,
    sp_dl_return: bytes | None = b"data",
    sp_dl_side_effect: Exception | None = None,
    sp_ul_side_effect: Exception | None = None,
) -> Generator[tuple[Mock, Mock, Mock, Mock]]:
    """Patch all engine methods with optional overrides for return/side effects."""
    with (
        patch(
            "connector.engine.UploadToS3Engine.download_file",
            autospec=True,
            return_value=s3_dl_return,
            side_effect=s3_dl_side_effect,
        ) as s3_dl,
        patch(
            "connector.engine.UploadToS3Engine.upload_file",
            autospec=True,
            side_effect=s3_ul_side_effect,
        ) as s3_ul,
        patch(
            "connector.engine.UploadToSharePointEngine.download_file",
            autospec=True,
            return_value=sp_dl_return,
            side_effect=sp_dl_side_effect,
        ) as sp_dl,
        patch(
            "connector.engine.UploadToSharePointEngine.upload_file",
            autospec=True,
            side_effect=sp_ul_side_effect,
        ) as sp_ul,
    ):
        yield (s3_dl, s3_ul, sp_dl, sp_ul)


@pytest.fixture(autouse=True)
def suppress_engine_init() -> Generator[None]:
    """Prevent Engine.__post_init__ from running real connector setup in all tests."""
    with patch("connector.engine.Engine.__post_init__"):
        yield


class TestRunWriteToS3:
    """A/B: run() called with mode='write_to_s3' and data_movement_plan as args."""

    def test_s3_engine_called_not_sharepoint(self) -> None:
        """Test that UploadToS3Engine is used and SharePointEngine is never called."""
        plans_dicts, _ = create_sp_to_s3_movement_plan()

        with mock_all_engines() as (s3_dl, s3_ul, sp_dl, sp_ul):
            run(mode="write_to_s3", data_movement_plan=plans_dicts)

        num_files = len(plans_dicts)
        assert s3_dl.call_count == num_files
        assert s3_ul.call_count == num_files
        assert sp_dl.call_count == 0
        assert sp_ul.call_count == 0

    def test_each_file_uses_correct_plan(self) -> None:
        """Test that each engine call receives the plan matching its position."""
        plans_dicts, expected = create_sp_to_s3_movement_plan()

        with mock_all_engines() as (s3_dl, _, __, ___):
            run(mode="write_to_s3", data_movement_plan=plans_dicts)

        for i, call_args in enumerate(s3_dl.call_args_list):
            engine_instance = call_args[0][0]
            assert isinstance(engine_instance, engine_module.UploadToS3Engine)
            assert isinstance(engine_instance.secrets, SecretConfig)
            assert engine_instance.plan == expected.data_to_move[i]


class TestRunWriteToSharePoint:
    """run() with mode='write_to_sharepoint' and data_movement_plan as args."""

    def test_sp_engine_called_not_s3(self) -> None:
        """Test that UploadToSharePointEngine is used and S3Engine is never called."""
        plans_dicts, _ = create_s3_to_sp_movement_plan()

        with mock_all_engines() as (s3_dl, s3_ul, sp_dl, sp_ul):
            run(mode="write_to_sharepoint", data_movement_plan=plans_dicts)

        n = len(plans_dicts)
        assert sp_dl.call_count == n
        assert sp_ul.call_count == n
        assert s3_dl.call_count == 0
        assert s3_ul.call_count == 0

    def test_each_file_uses_correct_plan(self) -> None:
        """Test that each engine call receives the plan matching its position."""
        plans_dicts, expected = create_s3_to_sp_movement_plan()

        with mock_all_engines() as (_, __, sp_dl, ___):
            run(mode="write_to_sharepoint", data_movement_plan=plans_dicts)

        for i, call_args in enumerate(sp_dl.call_args_list):
            engine_instance = call_args[0][0]
            assert isinstance(engine_instance, engine_module.UploadToSharePointEngine)
            assert isinstance(engine_instance.secrets, SecretConfig)
            assert engine_instance.plan == expected.data_to_move[i]


def test_upload_result_passed_to_upload_file() -> None:
    """Test that the bytes returned by download_file are passed to upload_file."""
    plans_dicts, _ = create_sp_to_s3_movement_plan()
    fake_content = b"test-file-content"

    with mock_all_engines(s3_dl_return=fake_content) as (_, s3_ul, __, ___):
        run(mode="write_to_s3", data_movement_plan=plans_dicts)

    for call_args in s3_ul.call_args_list:
        assert call_args[0][1] == fake_content


class TestRunFromEnvVars:
    """run() with mode and/or data_movement_plan resolved from env vars."""

    def test_both_mode_and_plan_from_env_vars(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that run() works correctly with both values sourced from env vars."""
        plans_dicts, expected = create_sp_to_s3_movement_plan()
        monkeypatch.setenv("MODE", "write_to_s3")
        monkeypatch.setenv("DATA_MOVEMENT_PLAN", json.dumps(plans_dicts))

        with mock_all_engines() as (s3_dl, s3_ul, _, __):
            run()

        assert s3_dl.call_count == len(plans_dicts)
        assert s3_ul.call_count == len(plans_dicts)

        for i, call_args in enumerate(s3_dl.call_args_list):
            assert call_args[0][0].plan == expected.data_to_move[i]

    def test_env_plan_single_dict_wrapped_to_list(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that a single dict in DATA_MOVEMENT_PLAN env var yields one plan."""
        plans_dicts, _ = create_sp_to_s3_movement_plan()
        single_plan = plans_dicts[0]
        monkeypatch.setenv("DATA_MOVEMENT_PLAN", json.dumps(single_plan))

        with mock_all_engines() as (s3_dl, s3_ul, _, __):
            run(mode="write_to_s3")

        assert s3_dl.call_count == 1
        assert s3_ul.call_count == 1


class TestRunErrorPaths:
    """run() validation and error propagation."""

    def test_invalid_mode_raises_value_error(self) -> None:
        """Test that an invalid mode string raises ValueError."""
        plans_dicts, _ = create_sp_to_s3_movement_plan()

        with pytest.raises(ValueError, match="Invalid mode"):
            run(mode="invalid_mode", data_movement_plan=plans_dicts)  # type: ignore[arg-type]

    def test_no_mode_raises_value_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that omitting mode with no MODE env var raises ValueError."""
        monkeypatch.delenv("MODE", raising=False)
        plans_dicts, _ = create_sp_to_s3_movement_plan()

        with pytest.raises(ValueError, match="Invalid mode"):
            run(data_movement_plan=plans_dicts)

    def test_no_movement_plan_raises_value_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test missing plan with no DATA_MOVEMENT_PLAN env var raises ValueError."""
        monkeypatch.delenv("DATA_MOVEMENT_PLAN", raising=False)

        with pytest.raises(ValueError, match="No data movement plan"):
            run(mode="write_to_s3")

    def test_upload_error_propagates(self) -> None:
        """Test that an UploadError raised during download is re-raised by run()."""
        plans_dicts, _ = create_sp_to_s3_movement_plan()

        with (
            mock_all_engines(s3_dl_side_effect=UploadError("download failed")),
            pytest.raises(UploadError, match="download failed"),
        ):
            run(mode="write_to_s3", data_movement_plan=plans_dicts)

    def test_upload_error_on_upload_propagates(self) -> None:
        """Test that an UploadError raised during upload is re-raised by run()."""
        plans_dicts, _ = create_sp_to_s3_movement_plan()

        with (
            mock_all_engines(s3_ul_side_effect=UploadError("upload failed")),
            pytest.raises(UploadError, match="upload failed"),
        ):
            run(mode="write_to_s3", data_movement_plan=plans_dicts)

    def test_upload_error_stops_remaining_files(self) -> None:
        """Test UploadError on file one prevents remaining files from running."""
        plans_dicts, _ = create_sp_to_s3_movement_plan()

        with (
            mock_all_engines(s3_dl_side_effect=UploadError("fail on first")) as (
                s3_dl,
                _,
                __,
                ___,
            ),
            pytest.raises(UploadError),
        ):
            run(mode="write_to_s3", data_movement_plan=plans_dicts)

        assert s3_dl.call_count == 1
