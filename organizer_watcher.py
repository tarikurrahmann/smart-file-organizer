from __future__ import annotations

import os
import queue
import threading
import time
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, pyqtSignal
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from organizer import organize_file


INCOMPLETE_EXTENSIONS = {
    ".crdownload",
    ".download",
    ".filepart",
    ".part",
    ".partial",
    ".tmp",
}


class _OrganizerEventHandler(FileSystemEventHandler):
    def __init__(self, enqueue_path: Callable[[Path], None]) -> None:
        self.enqueue_path = enqueue_path

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.enqueue_path(Path(os.fsdecode(event.src_path)))

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.enqueue_path(Path(os.fsdecode(event.dest_path)))


class LiveFolderOrganizer(QObject):
    file_organized = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, folder: str | Path) -> None:
        super().__init__()
        self.folder = Path(folder).expanduser().resolve(strict=True)
        if not self.folder.is_dir():
            raise NotADirectoryError(f"Not a folder: {self.folder}")

        self._queue: queue.Queue[Path | None] = queue.Queue()
        self._queued: set[Path] = set()
        self._queue_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._observer: BaseObserver | None = None
        self._worker: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()

    def start(self) -> None:
        if self.is_running:
            return

        observer = Observer()
        observer.schedule(
            _OrganizerEventHandler(self._enqueue_path),
            str(self.folder),
            recursive=False,
        )
        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._process_queue,
            name="smart-file-live-organizer",
            daemon=True,
        )
        self._worker.start()
        try:
            observer.start()
        except OSError:
            self._stop_event.set()
            self._queue.put(None)
            self._worker.join(timeout=2)
            self._worker = None
            raise
        self._observer = observer

    def stop(self) -> None:
        self._stop_event.set()
        observer = self._observer
        self._observer = None
        if observer is not None:
            observer.stop()
            observer.join(timeout=3)
            if observer.is_alive():
                self.error_occurred.emit("The folder watcher did not stop cleanly.")

        self._queue.put(None)
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.join(timeout=3)
            if worker.is_alive():
                self.error_occurred.emit("The organizer worker did not stop cleanly.")

    def _enqueue_path(self, path: Path) -> None:
        try:
            if path.suffix.lower() in INCOMPLETE_EXTENSIONS or path.name.startswith("~$"):
                return
            if path.is_symlink():
                return
            resolved_path = path.resolve(strict=False)
            if resolved_path.parent != self.folder:
                return
            with self._queue_lock:
                if resolved_path in self._queued:
                    return
                self._queued.add(resolved_path)
            self._queue.put(resolved_path)
        except OSError as error:
            self.error_occurred.emit(f"{path}: {error}")

    def _wait_until_stable(self, path: Path) -> bool:
        last_signature: tuple[int, int] | None = None
        stable_since: float | None = None
        deadline = time.monotonic() + 300

        while not self._stop_event.is_set() and time.monotonic() < deadline:
            try:
                if path.is_symlink() or not path.is_file():
                    return False
                stat = path.stat()
                signature = (stat.st_size, stat.st_mtime_ns)
            except FileNotFoundError:
                return False
            except OSError:
                self._stop_event.wait(0.5)
                continue

            if signature == last_signature:
                if stable_since is None:
                    stable_since = time.monotonic()
                elif time.monotonic() - stable_since >= 2:
                    return True
            else:
                last_signature = signature
                stable_since = None
            self._stop_event.wait(0.5)

        if not self._stop_event.is_set():
            self.error_occurred.emit(f"Timed out waiting for file write to finish: {path}")
        return False

    def _process_queue(self) -> None:
        while not self._stop_event.is_set():
            try:
                path = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if path is None:
                break

            try:
                if not self._wait_until_stable(path):
                    continue
                target = organize_file(path)
                self.file_organized.emit(str(path), str(target))
            except (OSError, ValueError) as error:
                self.error_occurred.emit(f"{path}: {error}")
            finally:
                with self._queue_lock:
                    self._queued.discard(path)
