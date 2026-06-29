"""Unit tests for scripts.versioning helpers and CLI commands."""

from urllib.error import HTTPError

import pytest

from scripts.versioning import validate_newer_version


class _DummyUrlResponseContext:
    """Stub urlopen for testing purposes."""

    def __enter__(self) -> object:
        return object()

    def __exit__(self, *args: object) -> bool:
        return False

def test_validate_newer_version_allows_missing_package_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Assume a 404 means the package is not published yet, so validation passes."""
    http_error = HTTPError(
        url="https://pypi.org/pypi/aws-sharepoint-connector/json",
        code=404,
        msg="Not Found",
        hdrs=None,
        fp=None,
    )

    def fake_urlopen(*_: object, **__: object) -> None:
        raise http_error

    monkeypatch.setattr("scripts.versioning.urllib.request.urlopen", fake_urlopen)

    validate_newer_version(version="1.0.0")


def test_validate_newer_version_raises_for_non_404_http_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HTTP errors other than 404 should still fail validation."""
    http_error = HTTPError(
        url="https://pypi.org/pypi/aws-sharepoint-connector/json",
        code=500,
        msg="Server Error",
        hdrs=None,
        fp=None,
    )

    def fake_urlopen(*_: object, **__: object) -> None:
        raise http_error

    monkeypatch.setattr("scripts.versioning.urllib.request.urlopen", fake_urlopen)

    with pytest.raises(HTTPError):
        validate_newer_version(version="1.0.0")


def test_validate_newer_version_passes_when_candidate_is_newer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validation should pass when candidate version is newer."""

    def fake_urlopen(*_: object, **__: object) -> _DummyUrlResponseContext:
        return _DummyUrlResponseContext()

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

    def fake_urlopen(*_: object, **__: object) -> _DummyUrlResponseContext:
        return _DummyUrlResponseContext()

    monkeypatch.setattr("scripts.versioning.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(
        "scripts.versioning.json.load",
        lambda _response: {"releases": {"1.0.0": {}, "1.1.0": {}}},
    )

    with pytest.raises(SystemExit, match="not newer"):
        validate_newer_version(version="1.1.0")
