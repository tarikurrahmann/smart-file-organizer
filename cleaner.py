from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from send2trash import send2trash


JUNK_EXTENSIONS = {".tmp", ".temp", ".cache"}


@dataclass(frozen=True)
class CleanupCandidate:
    path: Path
    size: int
    reason: str


@dataclass
class ScanResult:
    candidates: list[CleanupCandidate] = field(default_factory=list)
    total_size: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def reclaimable_size(self) -> int:
        return sum(candidate.size for candidate in self.candidates)


@dataclass
class CleanupResult:
    moved: list[CleanupCandidate] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def reclaimed_size(self) -> int:
        return sum(candidate.size for candidate in self.moved)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_folder(folder: str | Path) -> ScanResult:
    """Find exact duplicate copies and likely temporary files under a folder."""
    root = Path(folder).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"Not a folder: {root}")

    result = ScanResult()
    files_by_size: dict[int, list[Path]] = {}
    reasons: dict[Path, set[str]] = {}
    sizes: dict[Path, int] = {}

    def record_walk_error(error: OSError) -> None:
        result.errors.append(str(error))

    for current, directories, filenames in os.walk(root, followlinks=False, onerror=record_walk_error):
        directories[:] = [
            name for name in directories
            if not (Path(current) / name).is_symlink()
        ]
        for filename in filenames:
            path = Path(current) / filename
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                size = path.stat().st_size
            except OSError as error:
                result.errors.append(f"{path}: {error}")
                continue

            sizes[path] = size
            result.total_size += size
            files_by_size.setdefault(size, []).append(path)
            if path.suffix.lower() in JUNK_EXTENSIONS or filename.endswith("~") or filename.startswith("~$"):
                reasons.setdefault(path, set()).add("Temporary file")

    for same_size_files in files_by_size.values():
        if len(same_size_files) < 2:
            continue

        paths_by_hash: dict[str, list[Path]] = {}
        for path in same_size_files:
            try:
                paths_by_hash.setdefault(_file_hash(path), []).append(path)
            except OSError as error:
                result.errors.append(f"{path}: {error}")

        for identical_paths in paths_by_hash.values():
            if len(identical_paths) < 2:
                continue
            for duplicate in sorted(identical_paths)[1:]:
                reasons.setdefault(duplicate, set()).add("Duplicate copy")

    result.candidates = [
        CleanupCandidate(
            path=path,
            size=sizes[path],
            reason=", ".join(sorted(file_reasons)),
        )
        for path, file_reasons in sorted(reasons.items())
    ]
    return result


def move_to_trash(candidates: list[CleanupCandidate]) -> CleanupResult:
    """Send selected files to the operating system trash/recycle bin."""
    result = CleanupResult()
    for candidate in candidates:
        try:
            if not candidate.path.is_file() or candidate.path.is_symlink():
                result.errors.append(f"{candidate.path}: file no longer exists or is not a regular file")
                continue
            send2trash(str(candidate.path))
            result.moved.append(candidate)
        except OSError as error:
            result.errors.append(f"{candidate.path}: {error}")
    return result
