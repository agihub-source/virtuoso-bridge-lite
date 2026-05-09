"""Thread-safe JSONL log writer shared between MCP tools and the server."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

_lock = threading.Lock()
_path: str = "/tmp/vb_mcp_log.jsonl"


def init(path: str) -> None:
    global _path
    _path = path


def append(event: dict) -> None:
    line = json.dumps({"ts": time.strftime("%H:%M:%S"), **event}, ensure_ascii=False)
    with _lock:
        Path(_path).open("a", encoding="utf-8").write(line + "\n")
