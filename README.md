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

Operates in two modes: `write_to_s3` (SharePoint -> S3) and `write_to_sharepoint` (S3 -> SharePoint). Instantiate an engine via `create_engine` and call `copy` for each file you want to transfer.

## Table of contents

- [Architecture and flow](#architecture-and-flow)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Configuration and setup](#configuration-and-setup)
- [Installation](#installation)
- [Error handling and retries](#error-handling-and-retries)
- [How to modify or extend](#how-to-modify-or-extend)
- [Troubleshooting](#troubleshooting)
- [Security considerations](#security-considerations)
- [Changelog](CHANGELOG.md)
- [License](#license)

## Architecture and flow

### High level process flow

1. Create an engine with `create_engine(mode, sp_domain, sp_site, sp_library, s3_bucket)`
2. Identify the files you want to move, and their destination
3. For each file, call `engine.copy(source, destination)`:
    - Validates source and destination paths (and archive folder if supplied).
    - Calls engine validation checks before any file movement begins.
    - Download from the source system (SharePoint or S3).
    - Upload to the destination system (S3 or SharePoint).
    - Verify transfer was successful by comparing byte size.
    - For `write_to_sharepoint`, create missing destination folders automatically.
    - Optionally delete or archive the source file.
4. Returns a `Result` object confirming the copying was successful
5. Handle errors per file in your calling code.

### Transfer Modes

- **`write_to_s3`**: Download from SharePoint → Upload to S3
- **`write_to_sharepoint`**: Download from S3 → Upload to SharePoint

### Core Components

- `src/aws_sharepoint_connector/main.py`: Public API — `create_engine()`
- `src/aws_sharepoint_connector/config.py`: Pydantic models for validated configuration.
- `src/aws_sharepoint_connector/engine.py`: Abstract transfer logic.
- `src/aws_sharepoint_connector/output_models.py`: File metadata model returned by file listings.
- `src/aws_sharepoint_connector/sharepoint.py`: SharePoint connector.
- `src/aws_sharepoint_connector/s3.py`: AWS S3 connector.
- `src/aws_sharepoint_connector/auth.py`: Azure authentication and Graph utilities.
- `src/aws_sharepoint_connector/utils.py`: Logger, extension normalisation,
  path validation, and HTTP retry logic.

## Prerequisites

### Sharepoint site

You will require a Sharepoint site to serve as the source or destination for files; this can be a pre-existing Sharepoint site. It is the responsibility of the owner of the SharePoint site to maintain appropriate access controls for the data stored in the site; this library offers no mechanism for managing access to files.

### Azure app registration

1. An Azure app has to be registered in Entra ID. This will be bespoke to your project and will provide the connection to the Sharepoint site that `aws-sharepoint-connector` will make use of, using a secret key. To request a new Azure app and have it connected to your Sharepoint site, raise a demand request by following the [instructions here](https://user-guide.staff-identity.service.justice.gov.uk/documentation/guidance/appreg.html#application-registrations-sso). Your app will need the `sites.selected` permission. You can do this in terraform against the staff infrastructure authentication services repo (see [EM setup](https://github.com/ministryofjustice/staff-identity-idam-entra-infra/tree/main/terraform/envs/live/hmpps-electronic-monitoring-data) for an example), then post to [#staff-identity-authentication-services](https://moj.enterprise.slack.com/archives/C04AFS7TV7S).
2. You will then need to speak to the File and Data Management team, who will grant your app access to the specific sharepoint sites you need access to.

### Azure app details & secret

- You can view your [app registrations here](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade).
- Open up the app registration and the tenant ID will be available as `Directory (tenant) ID`.
- The client ID is available as `Application (client) ID`.
- The client secret is available from `manage` -> `certificates and secrets` - you may not be able to view it and instead may be sent it when the app is created.

### AWS access

- If running via airflow, or from within another repo that is running via airflow, then standard AP credentials and access management apply and will grant access to s3.


## Quick start

Install aws-sharepoint-connector from pypi and run the below (changing parameters to fit your s3 bucket, SharePoint site and files), you will also need to supply the secrets detailed below in [Configuration and setup](#configuration-and-setup)


```python
from aws_sharepoint_connector import create_engine

engine = create_engine(
    mode="write_to_s3",
    sp_domain="organisation.sharepoint.com",
    sp_site="analytics-site",
    sp_library="Documents",
    s3_bucket="my-bucket",
)

source_files = engine.list_source_files(
    search_folders=["reports/2026"],
    include_ext=["csv", ".json"],
    exclude_ext=["tmp"],
)

for source_file in source_files:
    result = engine.copy(source_file.path, f"transferred/{source_file.path}")
    print(result.target_url)
```

To archive a source after transfer, call `copy()` with
`source_handling="archive"` and provide `archive_folder`. Files with zero bytes are
skipped when uploading to SharePoint, with a log message.


## Configuration and setup

Configuration is parsed by the config classes in `src/aws_sharepoint_connector/config.py` which store
the S3 bucket, Sharepoint site and library and Azure App secrets

### Required Environment Variables

MUST be provided as secrets via airflow from AWS Secrets Manager.
DO NOT store as plain text

| Variable | Type | Description |
| --- | --- | --- |
| `SECRET_AZURE_TENANT_ID` | string | Azure tenant UUID for Graph API authentication |
| `SECRET_AZURE_CLIENT_ID` | string | Azure app registration client ID |
| `SECRET_AZURE_CLIENT_SECRET` | string | Azure app registration client secret (store in secret manager) |

---
---
---

### Required configuration variables

Passed directly to `create_engine()` from your calling code

**`create_engine(mode, sp_domain, sp_site, sp_library, s3_bucket)`**

| Argument | Type | Description |
| --- | --- | --- |
| `mode` | string | Transfer direction: `write_to_s3` or `write_to_sharepoint` |
| `sp_domain` | string | SharePoint domain (e.g. `organisation.sharepoint.com`) |
| `sp_site` | string | SharePoint site name (without URL prefix, e.g. `analytics-site`) |
| `sp_library` | string | SharePoint document library name (e.g. `Documents`) |
| `s3_bucket` | string | S3 bucket name (without `s3://` prefix) |

---
---
---

### The copy method

Passed to the engine's `copy` method to identify a specific file to move

**`copy(source, destination, archive_folder="", source_handling="none")`**

| Key | Type | Description |
| --- | --- | --- |
| `source` | string | Source file path (SharePoint path or S3 key) |
| `destination` | string | Destination file path (S3 key or SharePoint path) |
| `archive_folder` | Optional(string) | Folder to archive the source file into when `source_handling="archive"`. Must be a path in the same s3 bucket or SharePoint site. |
| `source_handling` | Optional(string) | What to do with source after successful transfer: `"none"` (default), `"delete"`, or `"archive"`. |


Returns a `Result` instance containing details of the transfer:

| Attribute | Type | Description |
| --- | --- | --- |
| `source` | string | Source file path (SharePoint path or S3 key). |
| `destination` | string | Destination file path (S3 key or SharePoint path). |
| `content_size` | int | Size of the transferred content in bytes. |
| `source_handling` | string | Source-handling mode: `"none"`, `"delete"`, or `"archive"`. |
| `status` | string | `"success"` when the transfer workflow completes, or `"skipped"` when the source file is empty and no upload or source handling is performed. |
| `target_url` | string | SharePoint file's `webUrl` or the destination's `s3://` URI. Empty when no destination URL is produced, such as for a skipped empty-file upload. |

---
---
---

### list file method

**`list_source_files(search_folders=None, include_ext=None, exclude_ext=None)`**

| Argument | Type | Description |
| --- | --- | --- |
| `search_folders` | Optional(list[string]) | Optional folder/prefix filters in the source system. Duplicate and overlapping folders are supported. |
| `include_ext` | Optional(list[string]) | Optional allow-list of file extensions. Accepts values with or without `.` and in any case. |
| `exclude_ext` | Optional(list[string]) | Optional deny-list of file extensions, applied after normalisation. |

Returns a list of `FileObject` instances, one for each matching file:

| Attribute | Type | Description |
| --- | --- | --- |
| `path` | string | File path relative to the source bucket or SharePoint library root. |
| `name` | string | File name, including its extension. |
| `created_datetime` | datetime \| None | File creation time, or `None` if unavailable. |
| `last_modified_datetime` | datetime \| None | File last-modified time, or `None` if unavailable. |

For S3 objects, both timestamp attributes contain S3's last-modified time.


## Installation

### Local install with `uv`

```bash
uv sync --all-groups --all-extras
```

### Package install in another project

Install from PyPI using your preferred package manager:

#### pip

```bash
pip install aws-sharepoint-connector
```

#### Poetry

```bash
poetry add aws-sharepoint-connector
```

#### uv

```bash
uv add aws-sharepoint-connector
```


### Running tests

```bash
uv run python -m pytest                        # all tests with coverage
uv run python -m pytest tests/unit             # unit tests only
uv run python -m pytest tests/e2e              # E2E tests (no real API calls)
```

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
- **Linear backoff** between retries: 0.5 seconds before the second attempt and 1 second before the third attempt

### Batch Processing Behavior

Batch iteration is handled by the calling code. The engine processes one file per `engine.copy()` call and raises `ProcessingError` on failure. It is the caller's responsibility to decide whether to abort or continue processing remaining files.

## How to modify or extend

### 1) Add a new transfer mode

1. Create a new engine class in `src/aws_sharepoint_connector/engine.py` implementing:
    - `_list_source_files(self, folders: list[str], include_ext: list[str], exclude_ext: list[str]) -> list[FileObject]`
    - `_download_file(self, source: str) -> bytes`
    - `_upload_file(self, content: bytes, destination: str, content_size: int) -> str`
    - `_archive_source_file(self, source: str, archive_folder: str, content_size: int) -> None`
    - `_delete_source_file(self, source: str) -> None`
    - `_validate_plan(self, source: str, destination: str) -> None`
2. Register the engine in `MODE_MAP` in `src/aws_sharepoint_connector/main.py`.
3. Expand the `Literal` type for `mode` in `create_engine()` in `src/aws_sharepoint_connector/main.py`.
4. Add unit tests for success and failure paths, including `validate_plan` and source handling (`none`/`delete`/`archive`).

### 2) Add additional configuration

1. Add a field in `SecretConfig` (`src/aws_sharepoint_connector/config.py`).
2. Add validation if needed with a `field_validator`.
3. Update `.env` docs and this README.
4. Use the field in connector or engine logic.

## Troubleshooting

### Common errors and solutions

- **`Validation failed with N error(s)`**: One or more sources or destinations could not be verified before transfers started. The error message lists every problem - fix all of them before retrying.
- **`Library 'X' not found on site`**: Verify `sp_library` spelling and that the app has SharePoint access to the target site/library
- **`Source file not found in SharePoint`**: Verify the file exists at the exact path supplied as `source`; check case sensitivity
- **`InvalidPathError`**: The provided source, destination, or archive path was empty, absolute, or contained unsafe path segments (such as `..`).
- **`Destination folder not found in SharePoint`**: In `write_to_sharepoint` mode, missing destination folders are now created automatically; this error usually indicates permissions or object-type conflicts.
- **`S3 bucket does not exist`** or **`S3 object does not exist`**: Verify bucket name is correct, bucket exists in eu-west-2, and IAM principal has access
- **`Access denied to S3 bucket/object`**: Check IAM policy grants `s3:GetObject`, `s3:PutObject`, `s3:HeadObject`, and `s3:HeadBucket` on the bucket
- **`AADSTS65001` or Graph auth failures**: Verify app permissions and consent in Azure; may need admin consent
- **`File transfer failed: Max retries exceeded`**: File chunk upload exceeded 5 consecutive failures; check network stability, S3/SharePoint availability, and file size

## Security considerations

- **Never commit `.env` files or secrets**: Add `.env` to `.gitignore`
- **Prefer managed identity**: Use workload identity or managed identity in AWS/Azure instead of storing static credentials
- **Scope permissions tightly**:
    - Azure: Limit app permissions to only what the target site/library requires
  - AWS: Restrict IAM policy to specific bucket and prefix (e.g., `arn:aws:s3:::bucket/prefix/*`)
- **Rotate secrets**: Change Azure client secrets every 90 days and update secret manager
- **Store secrets securely**: Use AWS Secrets Manager, Azure Key Vault, or Kubernetes secrets (never hardcode in env vars)
- **Audit access**: Monitor S3 CloudTrail and SharePoint audit logs for sensitive data access
- **Network isolation**: Consider running connector in private network with appropriate egress controls
- **Data residency**: Ensure S3 bucket and SharePoint site comply with data residency requirements

## License

MIT License. See `LICENSE`.
