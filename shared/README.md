# Shared Contracts

## Recording upload

`POST /api/v1/recordings` accepts `multipart/form-data` with these fields:

| Field | Type | Description |
| --- | --- | --- |
| `audio` | WAV file | The completed PCM WAV recording. |
| `device_id` | string | Stable recorder identifier. |
| `filename` | string | Original SD-card filename, ending in `.wav`. |
| `sha256` | hex string | SHA-256 digest of the WAV bytes. |

The request must include `Authorization: Bearer <DEVICE_API_TOKEN>`. The API is
idempotent for a matching `device_id` and `sha256`: a repeated upload returns
HTTP 200; a new durable upload returns HTTP 201. The recorder may delete the
local file only for either of those responses.
