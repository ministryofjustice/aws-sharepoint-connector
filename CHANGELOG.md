# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.5.0] - 2026-07-01

### Changed

- Renamed the public transfer API from `engine.run(...)` to `engine.copy(...)`.
- Refactored engine internals to private workflow methods (`_validate_plan`, `_download_file`, `_upload_file`, `_archive_source_file`, `_delete_source_file`, `_copy`) while preserving transfer semantics.
- Moved `types-requests` from runtime dependencies to dev dependencies.
- Updated `README.md` and tests to align with the `copy(...)` API rename.

## [1.4.0] - 2026-06-30

### Added

- Added configurable post-transfer source handling via `engine.run(..., source_handling=...)`:
  - `none` (default): keep source in place
  - `delete`: delete source after successful transfer
  - `archive`: archive source after successful transfer (requires `archive_folder`)
- Added `NoArchiveFolderGivenError` when `source_handling="archive"` is used without an `archive_folder`.
- Added archive workflows in both transfer directions:
  - S3 source: copy to archive key and delete original object
  - SharePoint source: upload to archive path and delete original file

### Changed

- Updated `S3Connector` key management and verification flow to support destination/archive verification and source archiving.
- Updated `SharePointConnector` verification and archive handling with dedicated archive URL support.
- Updated `README.md` and API documentation to match runtime archive behavior.
- Expanded unit and integration tests for archive workflows and error handling.

### Fixed

- Corrected S3 verification semantics to verify destination/archive objects rather than source files during archive workflows.
- Corrected key handling in S3 archive code paths to avoid source/destination key confusion.

## [1.3.1] - 2026-06-29

### Changed

- Improved release/versioning script quality with typing and formatting updates.
- Added additional script-validation tests and coverage for release tooling.

### Fixed

- Allowed an initial `404` response during package-release copy initialisation to prevent false release failures.

## [1.3.0] - 2026-06-29

### Added

- Added semantic-release based versioning and release automation for package publishing.

### Changed

- Refined release workflow and versioning script logic to avoid direct pushes to `main`.
- Updated release-tool dependencies and packaging configuration for automation stability.

### Fixed

- Fixed multiple release-script path and file-handling issues, including Linux output parsing.
- Fixed release automation cleanup steps (including changelog and generated release artifacts handling).

## [1.2.3] - 2026-06-22

### Changed

- Updated `SharePointLibrary` and `S3Bucket` to inherit from `BaseModel` rather than `BaseSettings` so nested config objects are treated as data models instead of independently reading environment variables.

## [1.2.2] - 2026-06-17

### Added

- Exported engine classes in the top-level package API to simplify imports for consumers.

### Changed

- Updated project dependencies and linting-related configuration.
- Pinned `boto3` to `1.42.90` for dependency compatibility and stability.

## [1.2.1] - 2026-06-16

### Changed

- Refined SharePoint file-listing behaviour to correctly walk nested sub-folders.
- Rationalised transfer logging to improve consistency and diagnostics.
- Added and refined test coverage, including updates for Airflow-focused integration checks.
- Updated development dependencies (`moto`, `ruff`, `types-requests`, and `boto3`) and related CI workflow dependencies.

## [1.2.0] - 2026-06-16

### Added

- Expanded exception model with dedicated error types for clearer failure handling, including `InvalidModeError`, `ObjectNotFoundError`, and `IncorrectObjectTypeError`.
- Improved usage documentation in `README.md` covering engine creation and transfer flow with the simplified API.

### Changed

- Simplified the public transfer interface by fully removing movement-plan abstractions from runtime usage.
- `Engine.run(source, destination)` now performs validation automatically before transfer, so callers no longer need a separate validation call.
- SharePoint upload verification is now handled at the engine layer as part of the transfer pipeline.
- Updated transfer logic and tests to align with more specific exception behaviour and reporting.

## [1.1.0] - 2026-06-11

### Added

- Pre-flight validation via `engine.validate_plans(plans)` — must be called before iterating `engine.run()`. Checks all sources and destinations exist before any transfers begin, collecting every error into a single `UploadError` report so callers see the full picture at once.
  - `write_to_sharepoint` mode: verifies S3 bucket is accessible, each source S3 key exists, and each destination SharePoint parent folder exists.
  - `write_to_s3` mode: verifies S3 bucket is accessible and each source SharePoint file exists.
- `S3Connector.check_bucket_exists()` — raises `UploadError` with a descriptive message distinguishing "does not exist" (404) from "access denied" (403).
- `S3Connector.check_object_exists()` — same error-classification pattern for individual S3 keys.
- `SharePointConnector.check_file_exists(path)` — confirms a path in the SharePoint library is a file (not a folder or absent).
- `SharePointConnector.check_folder_exists(path)` — confirms a path in the SharePoint library is a folder (not a file or absent).

### Changed

- Replaced `run()` / `DATA_MOVEMENT_PLAN` env-var API with explicit factory functions:
  `create_engine(mode, sp_site, sp_library, s3_bucket)` and
  `create_movement_plan([{"source": str, "destination": str}])`
- Engine is created once per run and reused across all file transfers via `engine.run(source, destination)`
- `MovementPlan` now holds plain `source` / `destination` strings instead of nested typed objects
- Removed `DataMovementPlan`, `SharePointFile`, `S3File`, `S3ToSPMovementPlan`, `SPToS3MovementPlan` config models
- `SharePointConnector` no longer holds a file path at construction time; path is set per transfer via `update_with_file_path()`
- Removed `ensure_destination_folder` from `SharePointConnector`
- `mode` is now validated before secrets are loaded in `create_engine()`, so an invalid mode raises a clear `ValueError` immediately rather than a misleading secrets-missing error
- `s3_client` is created once at engine initialisation and reused for all transfers in that session (previously a new client was created for every download and upload call)
- `NoLibraryError` raised by `auth.get_drive_id` is now properly caught and re-raised as `UploadError` in `SharePointConnector.set_drive_id`, with a descriptive message including the site and library name
- Improved log messages throughout: transfer start/complete messages now include source path, destination path, and byte count

## [1.0.0] - 2026-05-14

### Added

- Batch file transfer support via `DATA_MOVEMENT_PLAN` environment variable configuration
- `MovementPlan` Pydantic models for declarative data movement configuration
- Parser to extract one or more movement plans from environment variables
- Validation for movement plan configs at startup

### Changed

- Refactored all connector components to operate on `MovementPlan` instances, replacing single-file configuration
- Exposed S3 and SharePoint parameters through a unified generic interface
- `ConnectorConfig` renamed to `SecretConfig`; `AppConfig` renamed to `ConnectorConfig`
- Simplified and refactored engine for improved robustness

### Fixed

- Minor environment variable loading issue

## [0.1.2] - 2026-05-06

### Changed

- Bumped Python base image to latest patch release

## [0.1.1] - 2026-05-06

### Added

- Non-secret arguments (e.g. SharePoint site name, library) can now be passed directly to the `main` entry point without requiring them to be stored in secrets

## [0.1.0] - 2026-05-06

### Added

- Core connector library (`auth`, `config`, `engine`, `s3`, `sharepoint`, `utils`, `exceptions` modules)
- Support for two transfer modes: `write_to_s3` (SharePoint → S3) and `write_to_sharepoint` (S3 → SharePoint) via Microsoft Graph API
- Chunked upload support for large files to SharePoint
- Verification step after upload to confirm file integrity
- `azure-identity`-based authentication using client credentials flow
- Pydantic-based configuration with `pydantic-settings` for environment variable parsing
- CLI entry point (`connector`) and programmatic API (`run()`)
- Custom exceptions: `NoLibraryError`, and others for structured error handling
- Logging with guard against duplicate log handlers
- `Dockerfile` for containerised deployment
- Full unit test suite (`pytest`, `moto` for S3 mocking)
- End-to-end test suite with mocked SharePoint and S3 interactions
- `pyproject.toml` with PDM/uv build backend, Ruff linting, and mypy strict type checking
- `README.md` with architecture diagram, configuration reference, and usage instructions

[1.2.0]: https://github.com/ministryofjustice/aws-sharepoint-connector/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/ministryofjustice/aws-sharepoint-connector/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/ministryofjustice/aws-sharepoint-connector/compare/v0.1.2...v1.0.0
[0.1.2]: https://github.com/ministryofjustice/aws-sharepoint-connector/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/ministryofjustice/aws-sharepoint-connector/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/ministryofjustice/aws-sharepoint-connector/releases/tag/v0.1.0
[1.2.3]: https://github.com/ministryofjustice/aws-sharepoint-connector/compare/v1.2.2...v1.2.3
[1.2.2]: https://github.com/ministryofjustice/aws-sharepoint-connector/compare/v1.2.1...v1.2.2
[1.2.1]: https://github.com/ministryofjustice/aws-sharepoint-connector/compare/v1.2.0...v1.2.1
[1.3.0]: https://github.com/ministryofjustice/aws-sharepoint-connector/compare/v1.2.3...v1.3.0
[1.3.1]: https://github.com/ministryofjustice/aws-sharepoint-connector/compare/v1.3.0...v1.3.1
[1.4.0]: https://github.com/ministryofjustice/aws-sharepoint-connector/compare/v1.3.1...v1.4.0
[1.5.0]: https://github.com/ministryofjustice/aws-sharepoint-connector/compare/v1.4.0...v1.5.0
[Unreleased]: https://github.com/ministryofjustice/aws-sharepoint-connector/compare/v1.5.0...HEAD
