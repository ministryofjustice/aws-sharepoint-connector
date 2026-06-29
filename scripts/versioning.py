"""Handle version logic."""

import json
import os
import urllib.error
import urllib.request

from packaging.version import Version
from typer import BadParameter, Typer, echo

app = Typer()

prod_url = "https://pypi.org/pypi/aws-sharepoint-connector/json"
test_url = "https://test.pypi.org/pypi/aws-sharepoint-connector/json"

MISSING_ERROR_CODE = 404

def check_url(url: str) -> None:
    """Check url is url and not file."""
    if not url.startswith(("http:", "https:")):
        msg = "URL must start with 'http:' or 'https:'"
        raise ValueError(msg)


@app.command("validate")
def validate_newer_version(version: str | None = None, url: str = prod_url) -> None:
    """Validate version is newer than current PyPI."""
    resolved_version = version or os.environ.get("CANDIDATE_VERSION")
    if not resolved_version:
        msg = "CANDIDATE_VERSION is required"
        raise BadParameter(msg)

    candidate = Version(resolved_version)
    check_url(url)
    try:
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 using check url first # nosec
            data = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == MISSING_ERROR_CODE:
            return
        raise

    releases = [Version(v) for v in data.get("releases", {})]
    if releases:
        latest = max(releases)
        if candidate <= latest:
            msg = f"Refusing to publish {candidate}:\
it is not newer than current PyPI latest {latest}."
            raise SystemExit(msg)


@app.command("check")
def check_test_version_exists(version: str | None = None, url: str = test_url) -> None:
    """Check if test package version already exists."""
    resolved_version = version or os.environ.get("VERSION")
    if not resolved_version:
        msg = "VERSION is required"
        raise BadParameter(msg)

    try:
        check_url(url)
        with urllib.request.urlopen(url, timeout=30) as response:  # noqa: S310 using check url first # nosec -
            data = json.load(response)
    except Exception:  # noqa: BLE001 just returning bool
        echo("false")
    else:
        exists = resolved_version in data.get("releases", {})
        echo("true" if exists else "false")


if __name__ == "__main__":
    app()
