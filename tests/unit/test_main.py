"""Test main functions."""

import pytest

from template.main import main


def test_main(capsys: pytest.CaptureFixture[str]) -> None:
    """Test main function."""
    main()

    captured = capsys.readouterr()
    assert captured.out == "Hello, World!\n"
