"""Structured JSON logging with secret masking.

Never logs: bot tokens, cookies, proxy passwords, full presigned URLs, secrets, initData.
"""
from __future__ import annotations

import logging
import re
import sys

import structlog

from .config import settings

# Patterns that must never reach logs. Order matters (broad last).
_MASK_PATTERNS = [
    re.compile(r"\d{6,}:[A-Za-z0-9_-]{30,}"),           # telegram bot token
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"),      # bearer tokens
    re.compile(r"://[^:/@\s]+:[^@/\s]+@"),               # user:pass@ in URLs
    re.compile(r"(?i)(password|passwd|secret|token|api_hash|initdata|cookie)([\"'=:\s]+)[^\s,;\"']+"),
]


def _mask(text: str) -> str:
    if not text:
        return text
    text = _MASK_PATTERNS[0].sub("<BOT_TOKEN>", text)
    text = _MASK_PATTERNS[1].sub(r"\1<REDACTED>", text)
    text = _MASK_PATTERNS[2].sub("://<REDACTED>@", text)
    text = _MASK_PATTERNS[3].sub(r"\1\2<REDACTED>", text)
    return text


def _mask_processor(logger, method_name, event_dict):
    for key, value in list(event_dict.items()):
        if isinstance(value, str):
            event_dict[key] = _mask(value)
    return event_dict


def configure_logging() -> None:
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    # These loggers emit full request URLs containing the bot token — silence them.
    for noisy in ("httpx", "httpcore", "telegram.ext.Application", "hpack", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _mask_processor,
        structlog.processors.StackInfoRenderer(),
    ]
    if settings.LOG_JSON:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "sharetube"):
    return structlog.get_logger(name)


def mask_secret(value: str, keep: int = 4) -> str:
    """Mask a secret keeping only the last `keep` chars, for safe display."""
    if not value:
        return ""
    if len(value) <= keep:
        return "*" * len(value)
    return "…" + value[-keep:]
