"""Structured JSON logging with request correlation IDs."""
from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
  def format(self, record: logging.LogRecord) -> str:
    payload: dict[str, Any] = {
      "ts": datetime.now(timezone.utc).isoformat(),
      "level": record.levelname,
      "logger": record.name,
      "message": record.getMessage(),
      "request_id": request_id_var.get(),
    }
    if record.exc_info:
      payload["exception"] = self.formatException(record.exc_info)
    for key in ("method", "path", "status_code", "duration_ms"):
      if hasattr(record, key):
        payload[key] = getattr(record, key)
    return json.dumps(payload, default=str)


def setup_logging() -> None:
  level_name = os.getenv("LOG_LEVEL", "INFO").upper()
  level = getattr(logging, level_name, logging.INFO)
  root = logging.getLogger()
  root.handlers.clear()
  handler = logging.StreamHandler(sys.stdout)
  handler.setFormatter(JsonFormatter())
  root.addHandler(handler)
  root.setLevel(level)
  logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def new_request_id() -> str:
  return uuid.uuid4().hex[:16]
