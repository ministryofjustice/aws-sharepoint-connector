"""Exceptions for the SharePoint connector."""


class InvalidModeError(Exception):
    """Raised when an invalid mode is provided to the connector."""


class ProcessingError(Exception):
    """Raised when an error occurs during processing of a file."""


class NoLibraryError(Exception):
    """Raised when the specified SharePoint library cannot be found on the site."""


class NoSiteError(Exception):
    """Raised when the specified SharePoint site cannot be found."""


class FileSizeMismatchError(Exception):
    """Raised when the uploaded file size does not match the expected size."""


class ObjectNotFoundError(Exception):
    """Raised when the specified object is not found in SharePoint or S3."""


class IncorrectObjectTypeError(Exception):
    """Raised when the object type is not as expected (e.g., file vs folder)."""
