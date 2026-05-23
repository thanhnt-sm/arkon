"""Upload size guard — reject oversized uploads early with 413 before RAM buffering.

Starlette spools multipart bodies to a SpooledTemporaryFile (1MB threshold), so the
multipart parse itself stays cheap. The OOM risk lives at `await file.read()`,
which materializes the full payload as `bytes`. Checking `file.size` (populated
by Starlette during parse) lets us 413 the request before that happens.
"""

from fastapi import HTTPException, UploadFile


def check_upload_size(file: UploadFile, max_mb: int) -> None:
    """Raise HTTP 413 if `file` exceeds `max_mb` megabytes.

    No-op if `file.size` is None (Starlette could not determine it — rare; in that
    case we accept and let downstream handle it).
    """
    if max_mb <= 0 or file.size is None:
        return
    limit_bytes = max_mb * 1024 * 1024
    if file.size > limit_bytes:
        size_mb = file.size / (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {size_mb:.1f}MB exceeds limit of {max_mb}MB",
        )
