from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class File_Object:
    path: str | None
    name: str
    created_datetime: datetime | None
    last_modified_datetime: datetime | None