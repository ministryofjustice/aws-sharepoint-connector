# AWS - SharePoint Connector

[![Python Unit Test](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-unit-test.yml/badge.svg)](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-unit-test.yml)
[![Python Linting](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-lint.yml/badge.svg)](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-lint.yml)
[![Python Type Check](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-type.yml/badge.svg)](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-type.yml)
[![Release Container](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/release-container.yml/badge.svg)](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/release-container.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)](pyproject.toml)

Provides a simple connector for moving files between AWS S3 and Microsoft SharePoint (via Microsoft Graph API).

Operates in one of two modes:

- `write_to_s3`: Download a file from SharePoint and upload it to S3.
- `write_to_sharepoint`: Download a file from S3 and upload it to SharePoint.

This repository is suitable for scheduled workloads (for example Airflow tasks, CI/CD jobs, or cron-style containers) where credentials and file metadata are provided through environment variables.

## Table of contents

- [Architecture and flow](#architecture-and-flow)
- [Configuration](#configuration)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [How to run](#how-to-run)
	- [Run locally (CLI)](#run-locally-cli)
	- [Run with Docker](#run-with-docker)
	- [Use as an import in another Python library](#use-as-an-import-in-another-python-library)
- [How to modify or extend](#how-to-modify-or-extend)
- [Operational notes](#operational-notes)
- [Troubleshooting](#troubleshooting)
- [Security considerations](#security-considerations)
- [License](#license)

## Architecture and flow

High-level runtime path:

1. Set environment variables (via airflow, or calling pipeline)
1. Load environment configuration with `AppConfig`.
2. Select engine from `MODE`:
	 - `UploadToS3Engine`
	 - `UploadToSharePointEngine`
3. Download file from source system.
4. Upload file to destination system.

Core components:

- `src/connector/main.py`: Entrypoint and engine selection.
- `src/connector/config.py`: Strongly typed environment settings via Pydantic.
- `src/connector/engine.py`: Transfer orchestration for each mode.
- `src/connector/sharepoint.py`: SharePoint Graph API connector.
- `src/connector/s3.py`: S3 object read/write connector.


## Configuration

All runtime configuration is environment-variable driven (or loaded from a local `.env` file during development).

| Variable | Required | Description | Example |
|---|---|---|---|
| `SECRET_AZURE_TENANT_ID` | Yes | Azure tenant UUID used for Graph auth | `00000000-0000-0000-0000-000000000000` |
| `SECRET_AZURE_CLIENT_ID` | Yes | Azure app registration client ID | `11111111-1111-1111-1111-111111111111` |
| `SECRET_AZURE_CLIENT_SECRET` | Yes | Azure app registration client secret | `super-secret` |
| `SP_SITE_NAME` | Yes | SharePoint site path segment used by Graph site lookup | `analytics-site` |
| `SP_LIBRARY_NAME` | Yes | Document library name in SharePoint | `Shared Documents` |
| `SP_FOLDER_PATH` | Yes | Target/source SharePoint folder path (trailing `/` auto-normalized) | `exports/reports/` |
| `SP_FILE_NAME` | Yes | Logical file name field in settings (currently not used for transfer key resolution) | `daily_report.csv` |
| `S3_BUCKET` | Yes | S3 bucket name | `my-transfer-bucket` |
| `FILE_KEY` | Yes | Object key used in S3 and appended to SharePoint folder path | `daily_report.csv` |
| `MODE` | Yes | Transfer direction | `write_to_s3` or `write_to_sharepoint` |

### How the SharePoint path variables combine

Given:

- `SP_SITE_NAME=analytics-site`
- `SP_LIBRARY_NAME=Shared Documents`
- `SP_FOLDER_PATH=exports/reports/2026/04/`
- `FILE_KEY=daily_report.csv`

The effective SharePoint location is:

- Site: `https://justiceuk.sharepoint.com/sites/analytics-site`
- Library: `Shared Documents`
- Folder path: `exports/reports/2026/04/`
- File path inside the library: `exports/reports/2026/04/daily_report.csv`

Full human-readable file URL example:

`https://justiceuk.sharepoint.com/sites/analytics-site/Shared%20Documents/exports/reports/2026/04/daily_report.csv`

Notes:

- The connector currently builds its Graph file path from `SP_FOLDER_PATH + FILE_KEY`.
- `SP_FILE_NAME` is present in config but is not used to build the transfer path today.

### Example `.env`

```env
SECRET_AZURE_TENANT_ID=00000000-0000-0000-0000-000000000000
SECRET_AZURE_CLIENT_ID=11111111-1111-1111-1111-111111111111
SECRET_AZURE_CLIENT_SECRET=replace_me

SP_SITE_NAME=analytics-site
SP_LIBRARY_NAME=Shared Documents
SP_FOLDER_PATH=exports/reports/
SP_FILE_NAME=daily_report.csv

S3_BUCKET=my-transfer-bucket
FILE_KEY=daily_report.csv

MODE=write_to_sharepoint
```

## Prerequisites

- Python `3.13+`
- [uv](https://docs.astral.sh/uv/) for dependency management
- Valid AWS credentials with access to target S3 bucket/object
- Azure AD application configured for Microsoft Graph access
- Network access to `graph.microsoft.com`, `login.microsoftonline.com`, and AWS S3 endpoints

## Installation

### Local install with `uv`

```bash
uv sync
```

Install development and test groups:

```bash
uv sync --all-groups
```

### Package install in another project

If your project uses `uv`, add this package from the public GitHub repo directly:

```bash
uv add "git+https://github.com/ministryofjustice/aws-sharepoint-connector.git"
```

Pin to a branch, tag, or commit if needed:

```bash
uv add "git+https://github.com/ministryofjustice/aws-sharepoint-connector.git@main"
uv add "git+https://github.com/ministryofjustice/aws-sharepoint-connector.git@v0.1.0"
uv add "git+https://github.com/ministryofjustice/aws-sharepoint-connector.git@<commit_sha>"
```

This updates your consuming project's `pyproject.toml` and lockfile via `uv`.

## How to run

### Run locally (CLI)

The package defines a script entrypoint named `connector`.

```bash
uv run connector
```

Equivalent direct module invocation:

```bash
uv run python src/connector/main.py
```

If `MODE=write_to_sharepoint`, data flow is:

1. Download object from `S3_BUCKET/FILE_KEY`
2. Upload object to SharePoint at `SP_FOLDER_PATH + FILE_KEY`

If `MODE=write_to_s3`, data flow is reversed.

### Run with Docker

Build image:

```bash
docker build -t aws-sharepoint-connector:local .
```

Run container with env file:

```bash
docker run --rm --env-file .env aws-sharepoint-connector:local
```

Run container with explicit environment overrides:

```bash
docker run --rm \
	-e SECRET_AZURE_TENANT_ID="00000000-0000-0000-0000-000000000000" \
	-e SECRET_AZURE_CLIENT_ID="11111111-1111-1111-1111-111111111111" \
	-e SECRET_AZURE_CLIENT_SECRET="replace_me" \  # pragma: allowlist secret
	-e SP_SITE_NAME="analytics-site" \
	-e SP_LIBRARY_NAME="Shared Documents" \
	-e SP_FOLDER_PATH="exports/reports/" \
	-e SP_FILE_NAME="daily_report.csv" \
	-e S3_BUCKET="my-transfer-bucket" \
	-e FILE_KEY="daily_report.csv" \
	-e MODE="write_to_s3" \
	aws-sharepoint-connector:local
```

The Docker image entrypoint is:

```bash
python src/connector/main.py
```

## Use as an import in another Python library

Import ```main``` from ```connector.main``` and call ```main()```.
You must have set all required environment variables first.

Secret values should be set via secret manager and airflow (e.g., client secret). Other values can be set in airflow, or directly in your code

### Example: set env vars then call `main()`

```python
import os

from connector.main import main


def run_transfer() -> None:
    os.environ["SECRET_AZURE_TENANT_ID"] = "Set in secret manager"
    os.environ["SECRET_AZURE_CLIENT_ID"] = "Set in secret manager"
    os.environ["SECRET_AZURE_CLIENT_SECRET"] = "Set in secret manager"  # pragma: allowlist secret
    os.environ["SP_SITE_NAME"] = "analytics-site"
    os.environ["SP_LIBRARY_NAME"] = "Shared Documents"
    os.environ["SP_FOLDER_PATH"] = "exports/reports/"
    os.environ["SP_FILE_NAME"] = "daily_report.csv"
    os.environ["S3_BUCKET"] = "my-transfer-bucket"
    os.environ["FILE_KEY"] = "daily_report.csv"
    os.environ["MODE"] = "write_to_sharepoint"

    main()
```

This runs the same code path as the CLI/Docker entrypoint.

## How to modify or extend

### 1) Add a new transfer mode

1. Create a new engine class in `src/connector/engine.py` implementing:
	 - `download_file(self) -> bytes`
	 - `upload_file(self, content: bytes) -> None`
2. Register the engine in `ENGINE_MAP` in `src/connector/main.py`.
3. Expand `MODE` literal options in `src/connector/config.py`.
4. Add unit tests for success and failure paths.

### 2) Add additional configuration

1. Add a field in `AppConfig` (`src/connector/config.py`).
2. Add validation if needed with a `field_validator`.
3. Update `.env` docs and this README.
4. Use the field in connector or engine logic.

### 3) Improve SharePoint or S3 behavior

- SharePoint-specific API logic is in `src/connector/sharepoint.py`.
- S3 calls are isolated in `src/connector/s3.py`.
- Retry behavior for HTTP chunk uploads is managed in `src/connector/utils.py`.

## Operational notes

- SharePoint uploads use chunked upload sessions (`10MB` chunks).
- Destination folder existence is validated before upload.
- Upload verification checks that the file exists in destination folder after chunk transfer.
- Logging is emitted to stdout for easy collection in containerized runtimes.

## Troubleshooting

- `Library 'X' not found on site`: verify `SP_LIBRARY_NAME` and site permissions.
- `Destination folder does not exist`: create `SP_FOLDER_PATH` in SharePoint first.
- `File not found in SharePoint`: validate `SP_FOLDER_PATH` and `FILE_KEY`.
- S3 read/write failures: check IAM policy, bucket policy, and key correctness.
- Auth failures: verify tenant ID, client ID/secret, and Graph API app permissions.

## Security considerations

- Never commit `.env` files or secrets.
- Prefer workload identity/managed identity where possible in runtime platforms.
- Scope AWS IAM and Azure Graph permissions to minimum required actions.
- Rotate client secrets regularly and store them in a secure secret manager.

## License

MIT License. See `LICENSE`.
