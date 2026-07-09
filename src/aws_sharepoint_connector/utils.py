"""Utility functions for the SharePoint connector."""

import logging
import sys
import time
from typing import TYPE_CHECKING, Any, Literal

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from aws_sharepoint_connector.constants import (
    MIN_PRINTABLE_ASCII,
    RETRYABLE_ERROR_CODES,
)
from aws_sharepoint_connector.exceptions import InvalidPathError

if TYPE_CHECKING:
    from collections.abc import Callable

log = logging.getLogger("s3-sharepoint")


def normalise_extension(extension: str) -> str:
    """Normalise a file extension to a lowercase, dot-free string.

    Args:
        extension (str): Raw extension, with or without a leading dot and in any case
        (e.g. ``".CSV"``).

    Returns:
        str: Normalised extension (e.g. ``"csv"``). Empty or whitespace-only entries are
        dropped.

    """
    return extension.strip().lower().lstrip(".")


def validate_path(path: str, field_name: str, *, allow_empty: bool = False) -> None:
    """Validate that a remote S3 or SharePoint path is safe to use.

    Guards against path traversal and injection by rejecting absolute paths,
    ``..`` segments, backslash separators, and control characters.

    Args:
        path (str): The path to validate.
        field_name (str): The name of the field being validated, used in errors.
        allow_empty (bool): Whether an empty path is permitted. Defaults to False.

    Raises:
        InvalidPathError: If the path is empty (when not allowed) or unsafe.

    """
    if not path:
        if allow_empty:
            return
        err = f"{field_name} must be a non-empty path."
        raise InvalidPathError(err)
    if any(ord(char) < MIN_PRINTABLE_ASCII for char in path):
        err = f"{field_name} contains invalid control characters: {path!r}"
        raise InvalidPathError(err)
    if "\\" in path:
        err = f"{field_name} must use '/' as the path separator: {path!r}"
        raise InvalidPathError(err)
    if path.startswith("/"):
        err = f"{field_name} must be a relative path, not absolute: {path!r}"
        raise InvalidPathError(err)
    if any(segment == ".." for segment in path.split("/")):
        err = f"{field_name} must not contain '..' path segments: {path!r}"
        raise InvalidPathError(err)


def setup_logger() -> logging.Logger:
    """Return a configured package logger with a stdout stream handler."""
    log = logging.getLogger("s3-sharepoint")
    log.setLevel(logging.INFO)
    if not log.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)
        log.addHandler(handler)

    return log


def build_retry_session() -> requests.Session:
    """Build a requests session with retry logic for transient errors."""
    session = requests.Session()
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "PUT"]),
        raise_on_status=False,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def request_with_retry(
    method: Literal["GET", "POST", "DELETE"],
    url: str,
    *,
    max_attempts: int = 3,
    **kwargs: Any,  # noqa: ANN401
) -> requests.Response:
    """Issue a request with bounded retries for transient failures.

    Args:
        method (Literal["GET", "POST", "DELETE"]): The HTTP method to use
        url (str): The URL to send the request to.
        max_attempts (int, optional): The maximum number of attempts to make.
            Defaults to 3.
        **kwargs: Additional arguments to pass to the request function.

    Returns:
        requests.Response: The response object from the request.

    Raises:
        ValueError: If an unsupported HTTP method is provided.
        requests.RequestException: If the request fails after the maximum
            number of attempts.

    """
    if method == "GET":
        request_fn: Callable[..., requests.Response] = requests.get
    elif method == "POST":
        request_fn = requests.post
    elif method == "DELETE":
        request_fn = requests.delete
    else:
        err = f"Unsupported HTTP method: {method}"
        raise ValueError(err)

    for attempt in range(1, max_attempts + 1):
        try:
            response = request_fn(url, **kwargs)
            if response.status_code in RETRYABLE_ERROR_CODES and attempt < max_attempts:
                log.warning(
                    "%s %s returned %s (attempt %s/%s), retrying...",
                    method,
                    url,
                    response.status_code,
                    attempt,
                    max_attempts,
                )
                time.sleep(0.5 * attempt)
            else:
                return response
        except requests.RequestException:
            if attempt == max_attempts:
                raise
            log.warning(
                "%s %s failed (attempt %s/%s), retrying...",
                method,
                url,
                attempt,
                max_attempts,
            )
            time.sleep(0.5 * attempt)

    # Unreachable: loop always returns or raises
    msg = f"Failed to execute {method} request to {url}"  # pragma: no cover
    raise RuntimeError(msg)  # pragma: no cover
