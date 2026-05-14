# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[Unreleased]: https://github.com/ministryofjustice/aws-sharepoint-connector/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/ministryofjustice/aws-sharepoint-connector/compare/v0.1.2...v1.0.0
[0.1.2]: https://github.com/ministryofjustice/aws-sharepoint-connector/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/ministryofjustice/aws-sharepoint-connector/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/ministryofjustice/aws-sharepoint-connector/releases/tag/v0.1.0
