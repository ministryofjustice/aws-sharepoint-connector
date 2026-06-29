"""Utility functions for the SharePoint connector."""

import logging
import sys
import time
from typing import TYPE_CHECKING, Any, Literal

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from aws_sharepoint_connector.constants import RETRYABLE_ERROR_CODES

if TYPE_CHECKING:
    from collections.abc import Callable

log = logging.getLogger("s3-sharepoint")


def setup_logger() -> logging.Logger:
    """Return a logger object and an io stream of the data that is logged."""
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
