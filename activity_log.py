from __future__ import annotations

import os
import platform
import shutil
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator


def _database_path() -> Path:
    if platform.system() == "Windows":
        base_directory = Path(
            os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
        )
    else:
        base_directory = Path(
            os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        )
    return base_directory / "SmartFileOrganizer" / "activity.sqlite3"


def _connect() -> sqlite3.Connection:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS organized_files (
            id INTEGER PRIMARY KEY,
            source TEXT NOT NULL,
            destination TEXT NOT NULL,
            category TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            action_id TEXT,
            undone INTEGER NOT NULL DEFAULT 0,
            undone_at TEXT
        )
        """
    )
    existing_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(organized_files)")
    }
    if "action_id" not in existing_columns:
        connection.execute("ALTER TABLE organized_files ADD COLUMN action_id TEXT")
    if "undone" not in existing_columns:
        connection.execute(
            "ALTER TABLE organized_files ADD COLUMN undone INTEGER NOT NULL DEFAULT 0"
        )
    if "undone_at" not in existing_columns:
        connection.execute("ALTER TABLE organized_files ADD COLUMN undone_at TEXT")
    connection.execute(
        "UPDATE organized_files SET action_id = 'legacy-' || id WHERE action_id IS NULL"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_organized_files_occurred_at "
        "ON organized_files(occurred_at DESC)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_organized_files_action "
        "ON organized_files(action_id, undone, id DESC)"
    )
    return connection


@contextmanager
def _connection() -> Generator[sqlite3.Connection, None, None]:
    connection = _connect()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def record_organized(
    source: str | Path,
    destination: str | Path,
    action_id: str | None = None,
) -> None:
    source_path = Path(source)
    destination_path = Path(destination)
    occurred_at = datetime.now().astimezone().isoformat(timespec="seconds")
    action_id = action_id or uuid.uuid4().hex
    try:
        with _connection() as connection:
            connection.execute(
                """
                INSERT INTO organized_files
                    (source, destination, category, occurred_at, action_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(source_path),
                    str(destination_path),
                    destination_path.parent.name,
                    occurred_at,
                    action_id,
                ),
            )
    except sqlite3.Error as error:
        raise OSError(f"Could not write activity history: {error}") from error


def activity_summary() -> tuple[int, dict[str, int]]:
    try:
        with _connection() as connection:
            total = connection.execute(
                "SELECT COUNT(*) FROM organized_files"
            ).fetchone()[0]
            rows = connection.execute(
                """
                SELECT category, COUNT(*)
                FROM organized_files
                GROUP BY category
                ORDER BY COUNT(*) DESC, category COLLATE NOCASE
                """
            ).fetchall()
    except sqlite3.Error as error:
        raise OSError(f"Could not read activity summary: {error}") from error
    return int(total), {str(category): int(count) for category, count in rows}


def recent_activity(
    limit: int = 200,
) -> list[tuple[str, str, str, str, bool]]:
    if limit < 1:
        raise ValueError("Activity history limit must be positive.")
    try:
        with _connection() as connection:
            rows = connection.execute(
                """
                SELECT occurred_at, category, source, destination, undone
                FROM organized_files
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    except sqlite3.Error as error:
        raise OSError(f"Could not read activity history: {error}") from error
    return [
        (
            str(occurred_at),
            str(category),
            str(source),
            str(destination),
            bool(undone),
        )
        for occurred_at, category, source, destination, undone in rows
    ]


def latest_undoable_action() -> tuple[str, int] | None:
    try:
        with _connection() as connection:
            row = connection.execute(
                """
                SELECT action_id, COUNT(*)
                FROM organized_files
                WHERE undone = 0
                GROUP BY action_id
                ORDER BY MAX(id) DESC
                LIMIT 1
                """
            ).fetchone()
    except sqlite3.Error as error:
        raise OSError(f"Could not read undo history: {error}") from error
    if row is None:
        return None
    return str(row[0]), int(row[1])


def undo_latest_action() -> tuple[int, list[str]]:
    action = latest_undoable_action()
    if action is None:
        return 0, []
    action_id, _ = action
    try:
        with _connection() as connection:
            rows = connection.execute(
                """
                SELECT id, source, destination
                FROM organized_files
                WHERE action_id = ? AND undone = 0
                ORDER BY id DESC
                """,
                (action_id,),
            ).fetchall()
    except sqlite3.Error as error:
        raise OSError(f"Could not read undo entries: {error}") from error

    moved_count = 0
    errors: list[str] = []
    for row_id, source_value, destination_value in rows:
        source = Path(source_value)
        destination = Path(destination_value)
        try:
            if source.exists() or source.is_symlink():
                errors.append(f"{source}: restore path already exists; left unchanged")
                continue
            if destination.is_symlink() or not destination.is_file():
                errors.append(f"{destination}: organized file is missing or not a regular file")
                continue
            shutil.move(str(destination), str(source))
            try:
                with _connection() as connection:
                    cursor = connection.execute(
                        """
                        UPDATE organized_files
                        SET undone = 1, undone_at = ?
                        WHERE id = ? AND undone = 0
                        """,
                        (
                            datetime.now().astimezone().isoformat(timespec="seconds"),
                            row_id,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise sqlite3.Error("Undo entry changed during restore.")
            except sqlite3.Error as error:
                try:
                    shutil.move(str(source), str(destination))
                except OSError as rollback_error:
                    errors.append(
                        f"{source}: undo history could not be updated ({error}); "
                        f"file remains restored because rollback failed ({rollback_error})"
                    )
                else:
                    errors.append(f"{source}: undo history could not be updated ({error})")
                continue
            moved_count += 1
        except OSError as error:
            errors.append(f"{destination}: {error}")
    return moved_count, errors
