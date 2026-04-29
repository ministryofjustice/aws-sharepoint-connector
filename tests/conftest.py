"""Pytest fixtures for testing the AWS SharePoint Connector."""

from collections.abc import Generator

import boto3
import pytest
from moto import mock_aws


@pytest.fixture(name="s3")
def mock_s3() -> Generator[boto3.client]:
    """Return a mocked s3 client."""
    with mock_aws():
        yield boto3.client("s3", region_name="eu-west-2")
