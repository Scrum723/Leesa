"""Watch inbox folders for new videos and enqueue them."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from . import db
from .config import Settings
from .logging_setup import EventLog

log = logging.getLogger("liaison.watcher")


class _VideoHandler(FileSystemEventHandler):
    def __init__(self, agent_watcher: "VideoWatcher") -> None:
        super().__init__()
        self.agent = agent_watcher

    def on_created(self, event):  # type: ignore[no-untyped-def]
        if event.is_directory:
            return
        self.agent.consider(Path(event.src_path))

    def on_moved(self, event):  # type: ignore[no-untyped-def]
        if event.is_directory:
            return
        self.agent.consider(Path(event.dest_path))


class VideoWatcher:
    def __init__(self, settings: Settings, events: EventLog | None = None) -> None:
        self.settings = settings
        self.events = events or EventLog()
        cfg = settings.config.get("watcher") or {}
        self.extensions = {e.lower() if e.startswith(".") else f".{e.lower()}" for e in cfg.get("extensions", [".mp4", ".mov"])}
        self.settle_seconds = float(cfg.get("settle_seconds", 8))
        self._observer: Observer | None = None
        self._stop = threading.Event()
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()

    def folders(self) -> list[Path]:
        folders = [self.settings.video_inbox]
        if self.settings.video_inbox_extra:
            folders.append(self.settings.video_inbox_extra)
        return folders

    def start(self) -> None:
        for folder in self.folders():
            folder.mkdir(parents=True, exist_ok=True)
        self.scan_existing()
        self._observer = Observer()
        handler = _VideoHandler(self)
        for folder in self.folders():
            self._observer.schedule(handler, str(folder), recursive=False)
            log.info("Watching video inbox: %s", folder)
        self._observer.start()
        t = threading.Thread(target=self._settle_loop, name="video-settle", daemon=True)
        t.start()

    def stop(self) -> None:
        self._stop.set()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None

    def scan_existing(self) -> int:
        count = 0
        for folder in self.folders():
            if not folder.exists():
                continue
            for path in sorted(folder.iterdir()):
                if path.is_file() and path.suffix.lower() in self.extensions:
                    if self.enqueue(path):
                        count += 1
        return count

    def consider(self, path: Path) -> None:
        if path.suffix.lower() not in self.extensions:
            return
        if path.name.startswith("."):
            return
        with self._lock:
            self._pending[str(path.resolve())] = time.time()

    def enqueue(self, path: Path) -> bool:
        path = path.resolve()
        if not path.exists() or not path.is_file():
            return False
        job_id = db.enqueue_video(str(path), path.name)
        if job_id:
            log.info("Queued video job #%s: %s", job_id, path.name)
            self.events.write("video_queued", job_id=job_id, path=str(path), filename=path.name)
            return True
        log.debug("Already known video: %s", path)
        return False

    def _settle_loop(self) -> None:
        while not self._stop.is_set():
            time.sleep(1)
            now = time.time()
            ready: list[str] = []
            with self._lock:
                for p, t0 in list(self._pending.items()):
                    if now - t0 < self.settle_seconds:
                        continue
                    # size stable check
                    path = Path(p)
                    try:
                        s1 = path.stat().st_size
                        time.sleep(0.4)
                        s2 = path.stat().st_size
                        if s1 == s2 and s1 > 0:
                            ready.append(p)
                            del self._pending[p]
                        else:
                            self._pending[p] = now
                    except FileNotFoundError:
                        del self._pending[p]
            for p in ready:
                self.enqueue(Path(p))
