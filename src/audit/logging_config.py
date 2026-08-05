"""Logging configuration with privacy scrubbing."""

from __future__ import annotations

import logging
import sys

from src.audit.privacy import SCRUBBER, ScrubbingFilter


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("src.audit")
    logger.handlers.clear()
    logger.setLevel(level)
    logger.propagate = False

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.addFilter(ScrubbingFilter(SCRUBBER))
    handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger
