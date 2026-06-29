"""Unit tests for scripts.versioning helpers and CLI commands."""

import typing
from email.message import Message
from urllib.error import HTTPError

import pytest
from typer import BadParameter

from scripts.versioning import check_test_version_exists, validate_newer_version


class _DummyUrlResponseContext:
    """Stub urlopen for testing purposes."""

    def __enter__(self) -> object:
        return object()

    def __exit__(self, *args: object) -> typing.Literal[False]:
        return False


def fake_urlopen_404(*_: object, **__: object) -> None:
    """Fake urlopen return 404 error."""
    http_error = HTTPError(
        url="https://pypi.org/pypi/aws-sharepoint-connector/json",
        code=404,
        msg="Not Found",
        hdrs=Message(),
        fp=None,
    )
    raise http_error


def fake_urlopen_500(*_: object, **__: object) -> None:
    """Fake urlopen return 500 error."""
    http_error = HTTPError(
        url="https://pypi.org/pypi/aws-sharepoint-connector/json",
        code=500,
        msg="Server Error",
        hdrs=Message(),
        fp=None,
    )
    raise http_error


def fake_urlopen(*_: object, **__: object) -> _DummyUrlResponseContext:
    """Fake url open to return dummy response."""
    return _DummyUrlResponseContext()


def test_validate_newer_version_allows_missing_package_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assume a 404 means the package is not published yet, so validation passes."""
    monkeypatch.setattr("scripts.versioning.urllib.request.urlopen", fake_urlopen_404)
    validate_newer_version(version="1.0.0")


def test_validate_newer_version_raises_for_non_404_http_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP errors other than 404 should still fail validation."""
    monkeypatch.setattr("scripts.versioning.urllib.request.urlopen", fake_urlopen_500)
    with pytest.raises(HTTPError):
        validate_newer_version(version="1.0.0")


def test_validate_newer_version_passes_when_candidate_is_newer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation should pass when candidate version is newer."""
    monkeypatch.setattr("scripts.versioning.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(
        "scripts.versioning.json.load",
        lambda _response: {"releases": {"1.0.0": {}, "1.1.0": {}}},
    )
    validate_newer_version(version="1.2.0")


def test_validate_newer_version_raises_when_candidate_is_not_newer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation should fail when candidate is same or older than latest release."""
    monkeypatch.setattr("scripts.versioning.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(
        "scripts.versioning.json.load",
        lambda _response: {"releases": {"1.0.0": {}, "1.1.0": {}}},
    )
    with pytest.raises(SystemExit, match="not newer"):
        validate_newer_version(version="1.1.0")


def test_check_test_version_exists_echoes_true_when_release_exists(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Check command outputs true when the target version exists."""
    monkeypatch.setattr("scripts.versioning.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(
        "scripts.versioning.json.load",
        lambda _response: {"releases": {"1.2.0": {}, "1.3.0": {}}},
    )
    check_test_version_exists(version="1.3.0")
    assert capsys.readouterr().out.strip() == "true"


def test_check_test_version_exists_echoes_false_when_release_missing(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Check command outputs false when the target version is absent."""
    monkeypatch.setattr("scripts.versioning.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(
        "scripts.versioning.json.load",
        lambda _response: {"releases": {"1.2.0": {}, "1.3.0": {}}},
    )
    check_test_version_exists(version="1.4.0")
    assert capsys.readouterr().out.strip() == "false"


def test_check_test_version_exists_echoes_false_when_request_errors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Check command outputs false when fetching release data fails."""
    monkeypatch.setattr("scripts.versioning.urllib.request.urlopen", fake_urlopen_404)
    check_test_version_exists(version="1.4.0")
    assert capsys.readouterr().out.strip() == "false"


def test_check_test_version_exists_raises_when_version_missing() -> None:
    """Check command requires VERSION argument or env var."""
    with pytest.raises(BadParameter, match="VERSION is required"):
        check_test_version_exists(version=None)
