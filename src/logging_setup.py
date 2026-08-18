"""Structured logging + JSONL event trail."""

from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import LOGS, ROOT


def setup_logging(cfg: dict[str, Any] | None = None) -> logging.Logger:
    cfg = cfg or {}
    level_name = str(cfg.get("level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)
    log_file = ROOT / cfg.get("file", "logs/liaison.log")
    log_file.parent.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)
    # Avoid duplicate handlers on reload
    if not root.handlers:
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)

        max_bytes = int(cfg.get("max_bytes", 10_485_760))
        backup = int(cfg.get("backup_count", 5))
        fh = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup, encoding="utf-8"
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)

    return logging.getLogger("liaison")


class EventLog:
    """Append-only JSONL for machine-readable history (posts, errors, alerts)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (LOGS / "events.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event_type: str, **payload: Any) -> None:
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")

    def tail(self, n: int = 100, event_type: str | None = None) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        out: list[dict[str, Any]] = []
        for line in reversed(lines):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event_type and obj.get("type") != event_type:
                continue
            out.append(obj)
            if len(out) >= n:
                break
        return list(reversed(out))
