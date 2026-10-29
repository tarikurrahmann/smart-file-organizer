from __future__ import annotations

import os
import queue
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, pyqtSignal
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from activity_log import record_organized


IMAGE_EXTENSIONS = {
    ".avif",
    ".bmp",
    ".gif",
    ".heic",
    ".heif",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


def _unique_destination(directory: Path, filename: str) -> Path:
    destination = directory / filename
    if not destination.exists():
        return destination

    original = Path(filename)
    counter = 1
    while True:
        candidate = directory / f"{original.stem} ({counter}){original.suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


class _ImageEventHandler(FileSystemEventHandler):
    def __init__(self, enqueue_path: Callable[[Path], None]) -> None:
        self.enqueue_path = enqueue_path

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.enqueue_path(Path(os.fsdecode(event.src_path)))

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.enqueue_path(Path(os.fsdecode(event.dest_path)))


class AutoImageSorter(QObject):
    image_sorted = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, source: str | Path, destination: str | Path) -> None:
        super().__init__()
        self.source = Path(source).expanduser().resolve(strict=True)
        self.destination = Path(destination).expanduser().resolve(strict=True)
        if not self.source.is_dir():
            raise NotADirectoryError(f"Not a source folder: {self.source}")
        if not self.destination.is_dir():
            raise NotADirectoryError(f"Not a destination folder: {self.destination}")

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

        handler = _ImageEventHandler(self._enqueue_path)
        observer = Observer()
        observer.schedule(handler, str(self.source), recursive=False)
        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._process_queue,
            name="smart-file-image-sorter",
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
                self.error_occurred.emit("The file watcher did not stop cleanly.")

        self._queue.put(None)
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.join(timeout=3)
            if worker.is_alive():
                self.error_occurred.emit("The image sorter worker did not stop cleanly.")

    def _enqueue_path(self, path: Path) -> None:
        try:
            if path.suffix.lower() not in IMAGE_EXTENSIONS:
                return
            if path.is_symlink():
                return
            resolved_path = path.resolve(strict=False)
            if resolved_path.parent != self.source:
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
            self.error_occurred.emit(f"Timed out waiting for image download to finish: {path}")
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
                date = datetime.now()
                target_dir = self.destination / f"Screenshots_{date.year}" / date.strftime("%Y-%m-%d")
                target_dir.mkdir(parents=True, exist_ok=True)
                target = _unique_destination(target_dir, path.name)
                shutil.move(str(path), str(target))
                try:
                    record_organized(path, target)
                except OSError as history_error:
                    try:
                        if path.exists() or path.is_symlink():
                            raise FileExistsError(
                                f"Original path is occupied: {path}"
                            )
                        shutil.move(str(target), str(path))
                    except OSError as rollback_error:
                        self.error_occurred.emit(
                            f"Activity history could not be saved ({history_error}); "
                            f"the image remains at {target} because it could not be "
                            f"restored ({rollback_error})."
                        )
                    else:
                        self.error_occurred.emit(
                            f"Activity history could not be saved; the image was "
                            f"restored to {path}: {history_error}"
                        )
                    continue
                self.image_sorted.emit(str(path), str(target))
            except OSError as error:
                self.error_occurred.emit(f"{path}: {error}")
            finally:
                with self._queue_lock:
                    self._queued.discard(path)
