import os

from loguru import logger

_FORMAT = "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {name}:{function}:{line} | {message}"


def setup_file_logging(filename: str) -> None:
    log_dir = os.environ.get("LOG_DIR", "/app/logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
        logger.add(
            os.path.join(log_dir, filename),
            rotation="50 MB",
            retention="14 days",
            level="DEBUG",
            enqueue=True,
            format=_FORMAT,
        )
    except Exception as _e:
        logger.warning(f"Could not enable file logging to {log_dir}: {_e}")
