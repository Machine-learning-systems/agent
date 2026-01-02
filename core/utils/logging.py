import sys
from pathlib import Path

from loguru import logger


def setup_logging(
    level: str = "INFO",
    log_file: str | Path | None = None,
    colorize: bool = True,
) -> None:
    """Configure loguru logging with console and optional file output."""
    logger.remove()

    format_str = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan> | "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stderr,
        format=format_str,
        level=level,
        colorize=colorize,
    )

    if log_file:
        logger.add(
            str(log_file),
            format=format_str,
            level=level,
            rotation="10 MB",
            retention="7 days",
            compression="zip",
        )


__all__ = ["logger", "setup_logging"]
