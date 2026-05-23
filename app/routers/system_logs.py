"""
System logs router — real-time and historical log access for admins.
Reads log files written by loguru to the shared /app/logs volume.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse, StreamingResponse

from app.database.models import Employee
from app.services.auth_service import require_permission

router = APIRouter(prefix="/system/logs", tags=["system-logs"])

LOG_DIR = Path(os.environ.get("LOG_DIR", "/app/logs"))

SOURCES = {
    "api": "api.log",
    "worker": "worker.log",
}


def _log_path(source: str) -> Optional[Path]:
    name = SOURCES.get(source)
    return LOG_DIR / name if name else None


def _tail(path: Path, n: int = 200) -> list[str]:
    """Return last n lines from file without loading it all into memory."""
    if not path.exists():
        return []
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            chunk = min(size, 1024 * 128)
            f.seek(-chunk, 2)
            raw = f.read().decode("utf-8", errors="replace")
        lines = raw.splitlines()
        return lines[-n:]
    except Exception:
        return []


@router.get("")
async def get_logs(
    source: str = Query("api"),
    lines: int = Query(200, ge=10, le=2000),
    level: Optional[str] = Query(None),
    _user: Employee = require_permission("audit.read"),
):
    path = _log_path(source)
    if path is None:
        return {"lines": [], "source": source, "available": False}

    raw = _tail(path, lines)

    if level:
        tag = f"| {level.upper():<8} |"
        raw = [line for line in raw if tag in line]

    return {
        "lines": raw,
        "source": source,
        "available": path.exists(),
        "total": len(raw),
        "sources": {k: (LOG_DIR / v).exists() for k, v in SOURCES.items()},
    }


@router.get("/stream")
async def stream_logs(
    source: str = Query("api"),
    _user: Employee = require_permission("audit.read"),
):
    """SSE endpoint — sends last 100 lines then streams new entries live."""
    path = _log_path(source)

    async def generate():
        if path is None or not path.exists():
            yield f"data: {json.dumps({'error': 'Log file not available', 'source': source})}\n\n"
            return

        # Send backlog
        for line in _tail(path, 100):
            if line.strip():
                yield f"data: {json.dumps({'line': line, 'source': source})}\n\n"

        # Heartbeat so browser keeps the connection alive
        yield "data: {\"ping\": true}\n\n"

        # Tail new content
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(0, 2)
                last_pos = f.tell()
                while True:
                    line = f.readline()
                    if line:
                        stripped = line.rstrip()
                        if stripped:
                            yield f"data: {json.dumps({'line': stripped, 'source': source})}\n\n"
                        last_pos = f.tell()
                    else:
                        # Detect log rotation (new file is smaller than last pos)
                        try:
                            current_size = path.stat().st_size
                            if current_size < last_pos:
                                f.seek(0)
                                last_pos = 0
                        except OSError:
                            pass
                        await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/download")
async def download_logs(
    source: str = Query("api"),
    _user: Employee = require_permission("audit.read"),
):
    from fastapi import HTTPException

    path = _log_path(source)
    if path is None or not path.exists():
        raise HTTPException(404, "Log file not found")

    return FileResponse(
        path=str(path),
        filename=f"arkon-{source}.log",
        media_type="text/plain",
    )
