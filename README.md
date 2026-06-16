# AWS - SharePoint Connector

[![GitHub release](https://img.shields.io/github/v/release/ministryofjustice/aws-sharepoint-connector)](https://github.com/ministryofjustice/aws-sharepoint-connector/releases)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Changelog](https://img.shields.io/badge/changelog-CHANGELOG.md-blue)](CHANGELOG.md)

[![Python Unit Test](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-unit-test.yml/badge.svg)](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-unit-test.yml)
[![Python Linting](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-lint.yml/badge.svg)](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-lint.yml)
[![Python Type Check](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-type.yml/badge.svg)](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-type.yml)
[![Release Container](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/release-container.yml/badge.svg)](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/release-container.yml)

Provides a simple connector for moving files between AWS S3 and Microsoft SharePoint (via Microsoft Graph API).

Operates in two modes: (`write_to_s3`) to move from AWS S3 and SharePoint and (`write_to_sharepoint`) to do the reverse. Simply instantiate an engine via `create_engine` and iterate over the source files you want to move with the `run` method.

## Table of contents

- [Architecture and flow](#architecture-and-flow)
- [Configuration](#configuration)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [How to run](#how-to-run)
  - [Programmatic API](#programmatic-api)
- [Error handling and retries](#error-handling-and-retries)
- [How to modify or extend](#how-to-modify-or-extend)
- [Troubleshooting](#troubleshooting)
- [Security considerations](#security-considerations)
- [Changelog](CHANGELOG.md)
- [License](#license)

## Architecture and flow

### High level process flow

1. Create an engine with `create_engine(mode, sp_site, sp_library, s3_bucket)`
2. Identify the files you want to move, and their destination
3. For each file, call `engine.run(source, destination)`:
    - Calls `engine.validate_plans` to validate the plan before any transfers begin:
    - Download from the source system (SharePoint or S3).
    - Upload to the destination system (S3 or SharePoint).
    - Verify transfer was successful by comparing byte size.
    - Optionally delete the source file
4. Handle errors per file in your calling code.

### Transfer Modes

- **`write_to_s3`**: Download from SharePoint → Upload to S3
- **`write_to_sharepoint`**: Download from S3 → Upload to SharePoint

### Core Components

- `src/connector/main.py`: Public API — `create_engine()`
- `src/connector/config.py`: Pydantic models for validated configuration.
- `src/connector/engine.py`: Abstract transfer logic.
- `src/connector/sharepoint.py`: SharePoint connector.
- `src/connector/s3.py`: AWS S3 connector.
- `src/connector/auth.py`: Azure authentication and Graph utilities.
- `src/connector/utils.py`: Logger and HTTP retry logic.

## Configuration

Configuration is parsed by the config classes in `src/connector/config.py` which store
the S3 bucket, Sharepoint site and library and Azure App secrets

### Required Environment Variables

MUST be provided as secrets via airflow from AWS Secrets Manager.
DO NOT store as plain text

| Variable | Type | Description |
| --- | --- | --- |
| `SECRET_AZURE_TENANT_ID` | string | Azure tenant UUID for Graph API authentication |
| `SECRET_AZURE_CLIENT_ID` | string | Azure app registration client ID |
| `SECRET_AZURE_CLIENT_SECRET` | string | Azure app registration client secret (store in secret manager) |

### Required configuration variables

Passed directly to `create_engine()` from your calling code

**`create_engine(mode, sp_site, sp_library, s3_bucket)`**

| Argument | Type | Description |
| --- | --- | --- |
| `mode` | string | Transfer direction: `write_to_s3` or `write_to_sharepoint` |
| `sp_site` | string | SharePoint site name (without URL prefix, e.g. `analytics-site`) |
| `sp_library` | string | SharePoint document library name (e.g. `Documents`) |
| `s3_bucket` | string | S3 bucket name (without `s3://` prefix) |

Passed to the engine's `run` method to identify a specific file to move

**`run(source, destination, delete)`**

| Key | Type | Description |
| --- | --- | --- |
| `source` | string | Source file path (SharePoint path or S3 key) |
| `destination` | string | Destination file path (S3 key or SharePoint path) |
| `delete` | bool | Flag for whether to delete source file after successful transfer |

### Example: SharePoint → S3 (single file)

For a SharePoint file at:
`https://justiceuk.sharepoint.com/sites/analytics-site/Documents/reports/2026/daily_report.csv`

To copy to `s3://my-bucket/path/to/daily_report.csv`:

```python
engine = create_engine(
    mode="write_to_s3",
    sp_site="analytics-site",
    sp_library="Documents",
    s3_bucket="my-bucket",
)
plans = [
    {
        "source": "reports/2026/daily_report.csv",
        "destination": "path/to/daily_report.csv",
    }
]
for plan in plans:
    engine.run(plan["source"], plan["destination"])
```

### Example: S3 → SharePoint (single file)

To move the same file in the other direction:

```python
engine = create_engine(
    mode="write_to_sharepoint",
    sp_site="analytics-site",
    sp_library="Documents",
    s3_bucket="my-bucket",
)
plans =
    {
        "source": "path/to/daily_report.csv",
        "destination": "reports/2026/daily_report.csv",
    }
]
for plan in plans:
    engine.run(plan["source"], plan["destination"])
```

## Prerequisites

### Sharepoint site

You will require a Sharepoint site to serve as the source or destination for files. This can be a pre-existing Sharepoint site, though you should be mindful of who will have access to the data.

### Azure app registration

An Azure app has to be registered in Entra ID. This will be bespoke to your project and provide the connection to the Sharepoint site and is what the connector will authenticate into via the secret key. To request a new Azure app and have it connected to your Sharepoint site, raise a demand request by following the [instructions here](https://user-guide.staff-identity.service.justice.gov.uk/documentation/guidance/appreg.html#application-registrations-sso). You can do this in terraform against the staff infrastructure authentication services repo (see [EM setup](https://github.com/ministryofjustice/staff-identity-idam-entra-infra/tree/main/terraform/envs/live/hmpps-electronic-monitoring-data) for an example), then post to [#staff-identity-authentication-services](https://moj.enterprise.slack.com/archives/C04AFS7TV7S).

The app will require these permissions:

- `sites.selected`

You will then need to speak to the File and Data Management team, who will grant your app access to the specific sharepoint sites you need access to.

### Azure app details & secret

You can view your [app registrations here](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade).

Open up the app registration and the tenant ID will be available as `Directory (tenant) ID`.

The client ID is available as `Application (client) ID`.

The client secret is available from `manage` -> `certificates and secrets` - you may not be able to view it and instead may be sent it when the app is created.

### AWS access

If running via airflow, or from within another repo that is running via airflow, then standard AP credentials and access management apply and will grant access to s3.

### Technical requirements

- Python `3.13+`
- [uv](https://docs.astral.sh/uv/) for dependency management

## Installation

### Local install with `uv`

```bash
uv sync --all-groups --all-extras
```

### Package install in another project

If your project uses `uv`, add this package from the public GitHub repo directly and pin to a specific commit SHA:

```bash
uv add "git+https://github.com/ministryofjustice/aws-sharepoint-connector.git@<commit_sha>"
```

### Running tests

```bash
uv run python -m pytest                        # all tests with coverage
uv run python -m pytest tests/unit             # unit tests only
uv run python -m pytest tests/e2e              # E2E tests (no real API calls)
```

## How to run

### Programmatic API

Import `create_engine` from the `connector` package.
The Azure secret values must be present as environment variables.

```python
from connector import create_engine

engine = create_engine(
    mode="write_to_s3",
    sp_site="analytics-site",
    sp_library="Documents",
    s3_bucket="my-bucket",
)

plans = [
    {
        "source": "reports/2026/daily_report.csv",
        "destination": "path/to/daily_report.csv",
    },
    {
        "source": "reports/2026/summary.csv",
        "destination": "path/to/summary.csv",
    },
]

for plan in plans:
    engine.run(plan.source, plan.destination)
```

You can optionally use the `list_source_files` methods on the engines to obtain a list
of all files in the S3 bucket or SharePoint library. This can be used to programmatically
build the list of plans to iterate over.

## Error handling and retries

The connector implements robust retry logic to handle transient failures.

### Chunk Upload Strategy

For large files, uploads are split into **10 MB chunks**:

- **Max 5 consecutive failures** per chunk before aborting the entire transfer
- **Transient errors** (429 Too Many Requests, 5xx): retried with exponential backoff
- **Permanent errors** (4xx excluding 429): immediately raised as `ProcessingError` without retry
- **File pointer reset** on every retry to ensure data consistency

Example: If a 50 MB file fails on chunk 3 of 5, the transfer aborts and raises `ProcessingError`.

### HTTP Request Retries

All Graph API and HTTP calls use `request_with_retry()`:

- **Max 3 attempts** per request
- **Retryable errors**: 429 Too Many Requests, 5xx Server Errors
- **Non-retryable errors**: 4xx Client Errors (except 429)
- **Exponential backoff** between retries

### Batch Processing Behavior

Batch iteration is handled by the calling code. The engine processes one file per `engine.run()` call and raises `ProcessingError` on failure. It is the caller's responsibility to decide whether to abort or continue processing remaining files.

## How to modify or extend

### 1) Add a new transfer mode

1. Create a new engine class in `src/connector/engine.py` implementing:
    - `download_file(self, source: str) -> bytes`
    - `upload_file(self, content: bytes, destination: str) -> None`
    - `validate_plans(self, plans: list[dict[str, str]]) -> None`
2. Register the engine in `MODE_MAP` in `src/connector/main.py`.
3. Expand the `Literal` type for `mode` in `create_engine()` in `src/connector/main.py`.
4. Add unit tests for success and failure paths, including `validate_plans`.

### 2) Add additional configuration

1. Add a field in `SecretConfig` (`src/connector/config.py`).
2. Add validation if needed with a `field_validator`.
3. Update `.env` docs and this README.
4. Use the field in connector or engine logic.

## Troubleshooting

### Common errors and solutions

- **`Pre-flight validation failed with N error(s)`**: One or more sources or destinations could not be verified before transfers started. The error message lists every problem — fix all of them before retrying.
- **`Library 'X' not found on site`**: Verify `sp_library` spelling and that the app has SharePoint access via Graph API permissions (`Sites.Read.All`, `Files.ReadWrite.All`)
- **`Source file not found in SharePoint`**: Verify the file exists at the exact path supplied as `source`; check case sensitivity
- **`Destination folder not found in SharePoint`**: The parent directory of the destination path does not exist in SharePoint; create it before running the connector
- **`S3 bucket does not exist`** or **`S3 object does not exist`**: Verify bucket name is correct, bucket exists in eu-west-2, and IAM principal has access
- **`Access denied to S3 bucket/object`**: Check IAM policy grants `s3:GetObject`, `s3:PutObject`, `s3:HeadObject`, and `s3:HeadBucket` on the bucket
- **`AADSTS65001` or Graph auth failures**: Verify app permissions (`Sites.Read.All`, `Files.ReadWrite.All`) are granted in Azure; may need admin consent
- **`File transfer failed: Max retries exceeded`**: File chunk upload exceeded 5 consecutive failures; check network stability, S3/SharePoint availability, and file size

## Security considerations

- **Never commit `.env` files or secrets**: Add `.env` to `.gitignore`
- **Prefer managed identity**: Use workload identity or managed identity in AWS/Azure instead of storing static credentials
- **Scope permissions tightly**:
  - Azure: Limit app permissions to `Sites.Read.All` and `Files.ReadWrite.All` only
  - AWS: Restrict IAM policy to specific bucket and prefix (e.g., `arn:aws:s3:::bucket/prefix/*`)
- **Rotate secrets**: Change Azure client secrets every 90 days and update secret manager
- **Store secrets securely**: Use AWS Secrets Manager, Azure Key Vault, or Kubernetes secrets (never hardcode in env vars)
- **Audit access**: Monitor S3 CloudTrail and SharePoint audit logs for sensitive data access
- **Network isolation**: Consider running connector in private network with appropriate egress controls
- **Data residency**: Ensure S3 bucket and SharePoint site comply with data residency requirements

## License

MIT License. See `LICENSE`.
