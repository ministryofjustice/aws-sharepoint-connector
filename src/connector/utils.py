"""Utility functions for the SharePoint connector."""

import ast
import json
import logging
import sys

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


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


def parse_movement_plans_from_env(
    movement_plans: str,
) -> list[dict[str, str | list[dict[str, str]]]]:
    """Parse MOVEMENT_PLANS from an env var string into validated plan dicts.

    Supports both strict JSON and Python-literal-like input.
    """
    try:
        parsed_plans = json.loads(movement_plans)
    except json.JSONDecodeError:
        try:
            parsed_plans = ast.literal_eval(movement_plans)
        except (ValueError, SyntaxError) as exc:
            err = f"Failed to parse MOVEMENT_PLANS as JSON or Python literal: {exc}"
            raise ValueError(err) from exc

    if isinstance(parsed_plans, dict):
        return [parsed_plans]

    if isinstance(parsed_plans, list) and all(
        isinstance(item, dict) for item in parsed_plans
    ):
        return parsed_plans

    err = "MOVEMENT_PLANS must decode to a dict or a list of dicts."
    raise ValueError(err)
