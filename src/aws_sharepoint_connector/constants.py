"""Constants for the SharePoint connector."""

CHUNK_SIZE = 10 * 1024 * 1024  # 10MB, Graph requires chunked uploads for large files
SCOPE = "https://graph.microsoft.com/.default"
SHAREPOINT_DOMAIN = "justiceuk.sharepoint.com:"

DOES_NOT_EXIST_CODE = 404
BAD_REQUEST_CODE = 400
SERVER_ERROR_CODE = 500
TOO_MANY_REQUESTS_CODE = 429
RETRYABLE_ERROR_CODES = {429, 500, 502, 503, 504}
MAX_CHUNK_RETRIES = 5
ALREADY_EXISTS_CODE = 409

FILE_SIZE_TOLERANCE = {"msg": 20.000, "docx": 20.000, "xlsx": 20.000}
