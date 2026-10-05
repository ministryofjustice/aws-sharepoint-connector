"""Output models returned by connector operations."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FileObject:
    """Represent a file and its associated metadata."""

    path: str
    name: str
    created_datetime: datetime | None
    last_modified_datetime: datetime | None
