# AWS - SharePoint Connector

[![Python Unit Test](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-unit-test.yml/badge.svg)](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-unit-test.yml)
[![Python Linting](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-lint.yml/badge.svg)](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-lint.yml)
[![Python Type Check](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-type.yml/badge.svg)](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-type.yml)
[![Release Container](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/release-container.yml/badge.svg)](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/release-container.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)](pyproject.toml)

Provides a simple connector for moving files between AWS S3 and Microsoft SharePoint (via Microsoft Graph API).

Operates in two modes: download from SharePoint to S3 (`write_to_s3`), or upload from S3 to SharePoint (`write_to_sharepoint`). Supports both single-file and batch transfers via unified `DATA_MOVEMENT_PLAN` configuration.

## Table of contents

- [Architecture and flow](#architecture-and-flow)
- [Configuration](#configuration)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [How to run](#how-to-run)
	- [Run locally (CLI)](#run-locally-cli)
	- [Programmatic API](#programmatic-api)
- [Error handling and retries](#error-handling-and-retries)
- [How to modify or extend](#how-to-modify-or-extend)
- [Troubleshooting](#troubleshooting)
- [Security considerations](#security-considerations)
- [License](#license)

## Architecture and flow

### High level process flow

1. Load configuration from environment variables / function arguments.
2. Parse and validate `DATA_MOVEMENT_PLAN` with `DataMovementPlan` (`src/connector/config.py`).
3. Authenticate to Azure Graph API and AWS S3.
4. For each file in the batch:
	- Download from source system (SharePoint or S3).
	- Upload to destination system (S3 or SharePoint).
	- Verify destination file exists with matching size.
	- Log transfer status with file index and details.
5. Exit with error if any file fails; otherwise exit successfully.

### Transfer Modes

- **`write_to_s3`**: Download from SharePoint → Upload to S3
- **`write_to_sharepoint`**: Download from S3 → Upload to SharePoint

### Core Components

- `src/connector/main.py`: Entrypoint, CLI wrapper, batch orchestration.
- `src/connector/config.py`: Pydantic models for validated configuration.
- `src/connector/engine.py`: Abstract transfer logic.
- `src/connector/sharepoint.py`: SharePoint connector.
- `src/connector/s3.py`: AWS S3 connector.
- `src/connector/auth.py`: Azure authentication and Graph utilities.
- `src/connector/utils.py`: HTTP retry logic and environment parsing.

## Configuration

All configuration is parsed by the config classes in `src/connector/config.py` and can be supplied via:
- Environment variables
- Arguments passed to the `run` entry point in `src/connector/main.py`
- A .env file

### Required Environment Variables

Can ONLY be provided as environment variables from airflow (or .env)

| Variable | Type | Description |
|---|---|---|
| `SECRET_AZURE_TENANT_ID` | string | Azure tenant UUID for Graph API authentication |
| `SECRET_AZURE_CLIENT_ID` | string | Azure app registration client ID |
| `SECRET_AZURE_CLIENT_SECRET` | string | Azure app registration client secret (store in secret manager) |

### Additional Variables

Can be provided as environment variables or passed directly to `run`

| Variable | Type | Description |
|---|---|---|
| `MODE` | string | Transfer direction: `write_to_s3` or `write_to_sharepoint` |
| `DATA_MOVEMENT_PLAN` | JSON array | List of file transfer specifications (see [Data Movement Plan Schema](#data-movement-plan-schema)) |

### Data Movement Plan Schema

The `DATA_MOVEMENT_PLAN` must contain a JSON array of file transfer objects.

| Variable | Type | Description |
|---|---|---|
| `site` | string | Name of the Sharepoint site |
| `library` | string | Name of the document storage library |
| `directory` | string | Folder directories within the library |
| `filename` | string | Name of the file to read/write in Sharepoint |
| `bucket` | string | s3 bucket name |
| `key` | string | Full s3 file key to read/write |


### Example: Sharepoint → S3 (single file)

For a Sharepoint file located at:
https://justiceuk.sharepoint.com/sites/analytics-site/Documents/reports/2026/daily_report.csv

To copy to an s3 location of: s3://my-bucket/path/to/daily_report.csv

```json
data_movement_plan=[
  {
    "source": {
      "site": "analytics-site",
      "library": "Documents",
      "directory": "reports/2026/",
      "filename": "daily_report.csv"
    },
    "destination": {
      "bucket": "my-bucket",
      "key": "path/to/daily_report.csv"
    }
  }
]
```

### Example: S3 -> Sharepoint (single file)

And to move the same file the other way

```json
data_movement_plan=[
  {
    "source": {
      "bucket": "my-bucket",
      "key": "path/to/daily_report.csv"
    },
    "destination": {
      "site": "analytics-site",
      "library": "Documents",
      "directory": "reports/2026/",
      "filename": "daily_report.csv"
    }
  }
]
```

## Prerequisites

### Sharepoint site

You will require a Sharepoint site to serve as the source or destination for files. This can be a pre-existing Sharepoint site, though you should be mindful of who will have access to the data.

### Azure app registration

An Azure app has to be registered in Entra ID. This will be bespoke to your project and provide the connection to the Sharepoint site and is what the connector will authenticate into via the secret key. To request a new Azure app and have it connected to your Sharepoint site, raise a demand request by following the instructions [here](https://user-guide.staff-identity.service.justice.gov.uk/documentation/guidance/appreg.html#application-registrations-sso).

The app will require these permissions:
- `Sites.Read.All`
- `Files.ReadWrite.All`

### Azure app details & secret

You can view your app registrations [here](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade).

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
uv run pytest                        # all tests with coverage
uv run pytest tests/unit             # unit tests only
uv run pytest tests/e2e              # E2E tests (no real API calls)
```

## How to run

### Run locally (CLI)

The package defines a script entrypoint named `connector`. Set all variables in a `.env` file.

```bash
uv run connector
```

Equivalent direct module invocation:

```bash
uv run python src/connector/main.py
```

### Programmatic API

Import the `run()` function to use the connector in your Python code.
The secret values must be present in the environment variables.

```python
from connector import run

run(
    mode="write_to_s3",
    data_movement_plan=[
      {
        "source": {
          "site": "analytics-site",
          "library": "Documents",
          "directory": "reports/2026/",
          "filename": "daily_report.csv"
        },
        "destination": {
          "bucket": "my-bucket",
          "key": "path/to/daily_report.csv"
        }
      }
    ]
)
```

Or if all variables are stored in environment variables:

```python
from connector import run

run()
```

### Running from airflow

Example DAG using unified configuration:

```yaml
dag:
  repository: ministryofjustice/aws-sharepoint-connector
  tag: v1.0.0
  catchup: false
  depends_on_past: false
  is_paused_upon_creation: false
  max_active_runs: 4
  retries: 1
  retry_delay: 150
  start_date: "2026-01-01"
  schedule: None
  env_vars:
    MODE: write_to_s3
    DATA_MOVEMENT_PLAN: 'data_movement_plan=[
      {
        "source": {
          "site": "analytics-site",
          "library": "Documents",
          "directory": "reports/2026/",
          "filename": "daily_report.csv"
        },
        "destination": {
          "bucket": "my-bucket",
          "key": "path/to/daily_report.csv"
        }
      }
    ]
    '
  tasks:
    move_files:
      compute_profile: "general-on-demand-4vcpu-16gb"
iam:
  s3_read_write:
    - my-bucket

secrets:
  - azure-client-secret
  - azure-tenant-id
  - azure-client-id

maintainers:
  - [your-github-username]

tags:
  business_unit: OPG
  owner: [you@justice.gov.uk]
```

## Error handling and retries

The connector implements robust retry logic to handle transient failures.

### Chunk Upload Strategy

For large files, uploads are split into **10 MB chunks**:

- **Max 5 consecutive failures** per chunk before aborting the entire transfer
- **Transient errors** (429 Too Many Requests, 5xx): retried with exponential backoff
- **Permanent errors** (4xx excluding 429): immediately raised as `UploadError` without retry
- **File pointer reset** on every retry to ensure data consistency

Example: If a 50 MB file fails on chunk 3 of 5, the transfer aborts and raises `UploadError`.

### HTTP Request Retries

All Graph API and HTTP calls use `request_with_retry()`:

- **Max 3 attempts** per request
- **Retryable errors**: 429 Too Many Requests, 5xx Server Errors
- **Non-retryable errors**: 4xx Client Errors (except 429)
- **Exponential backoff** between retries

### Batch Processing Behavior

- **First failure stops batch**: If file 2 of 5 fails, remaining files (3–5) are not processed
- **Per-file logging**: Each file's status is logged with its index ("Processing file 2/5:", "Failed file 2/5:")
- **Error includes file identity**: Batch failure messages include which file failed and why

## How to modify or extend

### 1) Add a new transfer mode

1. Create a new engine class in `src/connector/engine.py` implementing:
	 - `download_file(self) -> bytes`
	 - `upload_file(self, content: bytes) -> None`
2. Register the engine in `ENGINE_MAP` in `src/connector/main.py`.
3. Expand `MODE` literal options in `src/connector/config.py`.
4. Add unit tests for success and failure paths.

### 2) Add additional configuration

1. Add a field in `SecretConfig` (`src/connector/config.py`).
2. Add validation if needed with a `field_validator`.
3. Update `.env` docs and this README.
4. Use the field in connector or engine logic.

### 3) Improve SharePoint or S3 behavior

- SharePoint-specific API logic is in `src/connector/sharepoint.py`.
- S3 calls are isolated in `src/connector/s3.py`.
- Retry behavior for HTTP chunk uploads is managed in `src/connector/utils.py`.


## Troubleshooting

### Common errors and solutions

- **`Library 'X' not found on site`**: Verify `library` spelling and that the app has SharePoint access via Graph API permissions (`Sites.Read.All`, `Files.ReadWrite.All`)
- **`Destination folder does not exist`**: Create the `directory` manually in SharePoint first, or use an existing folder
- **`File not found in SharePoint`**: Verify the file exists at the exact path `directory/filename`; check case sensitivity
- **`S3 NoSuchBucket` or `NoSuchKey`**: Verify bucket name is correct, bucket exists in eu-west-2, and IAM principal has access
- **`AccessDenied` (S3)**: Check IAM policy grants s3:GetObject/PutObject/HeadObject on the bucket
- **`AADSTS65001` or Graph auth failures**: Verify app permissions (Sites.Read.All, Files.ReadWrite.All) are granted in Azure; may need admin consent
- **`File transfer failed: Max retries exceeded`**: File chunk upload exceeded 5 consecutive failures; check network stability, S3/SharePoint availability, and file size
- **Batch processing stops after 1 file**: This is expected behavior; fix the failed file's configuration and rerun

## Security considerations

- **Never commit `.env` files or secrets**: Add `.env` to `.gitignore`
- **Prefer managed identity**: Use workload identity or managed identity in AWS/Azure instead of storing static credentials
- **Scope permissions tightly**:
  - Azure: Limit app permissions to `Sites.Read.All` and `Files.ReadWrite.All` only
  - AWS: Restrict IAM policy to specific bucket and prefix (e.g., `s3:arn:aws:s3:::bucket/prefix/*`)
- **Rotate secrets**: Change Azure client secrets every 90 days and update secret manager
- **Store secrets securely**: Use AWS Secrets Manager, Azure Key Vault, or Kubernetes secrets (never hardcode in env vars)
- **Audit access**: Monitor S3 CloudTrail and SharePoint audit logs for sensitive data access
- **Network isolation**: Consider running connector in private network with appropriate egress controls
- **Data residency**: Ensure S3 bucket and SharePoint site comply with data residency requirements

## License

MIT License. See `LICENSE`.
