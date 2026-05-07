# AWS - SharePoint Connector

[![Python Unit Test](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-unit-test.yml/badge.svg)](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-unit-test.yml)
[![Python Linting](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-lint.yml/badge.svg)](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-lint.yml)
[![Python Type Check](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-type.yml/badge.svg)](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/python-type.yml)
[![Release Container](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/release-container.yml/badge.svg)](https://github.com/ministryofjustice/aws-sharepoint-connector/actions/workflows/release-container.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)](pyproject.toml)

Provides a simple connector for moving files between AWS S3 and Microsoft SharePoint (via Microsoft Graph API).

Operates in two modes: download from SharePoint to S3 (write_to_s3), or upload from S3 to SharePoint (write_to_sharepoint).

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

1. Load configuration with `SecretConfig` (`src/connector/config.py`).
2. Select engine via `MODE` variable:
	- `UploadToS3Engine`
	- `UploadToSharePointEngine`
3. Download file from source system.
4. Upload file to destination system.
5. Verify file has been correctly written

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
| `SP_FILE_NAME` | Yes | Name of the file to be read from/written to Sharepoint | `daily_report.csv` |
| `S3_BUCKET` | Yes | S3 bucket name | `my-transfer-bucket` |
| `FILE_KEY` | Yes | s3 object key for the specific file to read or write to | `daily_report.csv` |
| `MODE` | Yes | Transfer direction | `write_to_s3` or `write_to_sharepoint` |

### How to define the SharePoint path variables

Given a full SharePoint file URL of:

`https://justiceuk.sharepoint.com/sites/analytics-site/Shared%20Documents/exports/reports/2026/04/daily_report.csv`

- `SP_SITE_NAME=analytics-site`
- `SP_LIBRARY_NAME=Shared Documents`
- `SP_FOLDER_PATH=exports/reports/2026/04/`
- `FILE_KEY=daily_report.csv`

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

The package defines a script entrypoint named `connector`. Define the required variables in a `.env` file or pass (the non secret ones) in as arguments.

```bash
uv run connector
```

Equivalent direct module invocation:

```bash
uv run python src/connector/main.py
```

### Run with Docker

Build image:

```bash
docker build -t aws-sharepoint-connector:local .
```

Run container with env file:

```bash
docker run --rm --env-file .env aws-sharepoint-connector:local
```

The Docker image entrypoint is:

```bash
python src/connector/main.py
```

### Running from airflow

Example DAG

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
    SP_SITE_NAME: analytics-site
    SP_LIBRARY_NAME: Shared Documents
    SP_FOLDER_PATH: exports/reports/
    SP_FILE_NAME: daily_report.csv
    S3_BUCKET: my-transfer-bucket
    FILE_KEY: daily_report.csv
    MODE: write_to_sharepoint
  tasks:
    move_file:
      compute_profile: "general-on-demand-4vcpu-16gb"
iam:
  s3_read_write:
    - my-transfer-bucket

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

## Use as an import in another Python library

```from connector import main``` and call ```main()```.
You must have set all required environment variables first (either via airflow, a .env file or setting os.environ directly), or pass them in as arguments to `main`.

Secret values should be set via secret manager and airflow (e.g., client secret).

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
