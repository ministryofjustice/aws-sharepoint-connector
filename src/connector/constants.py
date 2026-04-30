"""Constants for the SharePoint connector."""

CHUNK_SIZE = 10 * 1024 * 1024  # 10MB, Graph requires chunked uploads for large files
SCOPE = "https://graph.microsoft.com/.default"
SHAREPOINT_DOMAIN = "justiceuk.sharepoint.com:"

DOES_NOT_EXIST_CODE = 404
BAD_REQUEST_CODE = 400
