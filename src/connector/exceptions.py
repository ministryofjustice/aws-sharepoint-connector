"""Exceptions for the SharePoint connector."""


class UploadError(Exception):
    """Raised when any step of the SharePoint upload fails."""


class NoLibraryError(Exception):
    """Raised when the specified SharePoint library cannot be found on the site."""
