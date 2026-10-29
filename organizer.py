import shutil
import uuid
from pathlib import Path
from typing import Callable

from activity_log import record_organized
from custom_rules import load_custom_rules

# ক্যাটাগরি অনুযায়ী ফাইল এক্সটেনশনের ম্যাপিং
FILE_CATEGORIES = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp"],
    "Documents": [".pdf", ".docx", ".doc", ".txt", ".xlsx", ".pptx", ".csv"],
    "Videos": [".mp4", ".mkv", ".flv", ".avi", ".mov"],
    "Audio": [".mp3", ".wav", ".aac", ".flac"],
    "Archives": [".zip", ".rar", ".7z", ".tar", ".gz"],
    "Code": [".py", ".js", ".html", ".css", ".json", ".cpp", ".c", ".php"],
    "Executables": [".exe", ".msi", ".dmg"],
}


def organize_file(file_path, custom_rules=None, action_id=None):
    """Move one regular file into a category folder beside its current parent."""
    source_path = Path(file_path)
    if source_path.is_symlink() or not source_path.is_file():
        raise ValueError(f"Not a regular file: {source_path}")

    extension = source_path.suffix.lower()
    rules = load_custom_rules() if custom_rules is None else custom_rules
    destination_category = rules.get(extension)
    if destination_category is None:
        destination_category = "Others"
        for category, extensions in FILE_CATEGORIES.items():
            if extension in extensions:
                destination_category = category
                break

    target_folder = source_path.parent / destination_category
    target_folder.mkdir(exist_ok=True)
    target_path = target_folder / source_path.name

    counter = 1
    while target_path.exists():
        target_path = target_folder / (
            f"{source_path.stem}_{counter}{source_path.suffix}"
        )
        counter += 1

    destination_path = Path(shutil.move(str(source_path), str(target_path)))
    try:
        record_organized(source_path, destination_path, action_id)
    except OSError as history_error:
        try:
            if source_path.exists() or source_path.is_symlink():
                raise FileExistsError(
                    f"Original path is occupied: {source_path}"
                )
            shutil.move(str(destination_path), str(source_path))
        except OSError as rollback_error:
            raise OSError(
                f"Activity history could not be saved ({history_error}); "
                f"the file could not be restored and remains at {destination_path} "
                f"({rollback_error})."
            ) from rollback_error
        raise OSError(
            f"Activity history could not be saved; the file was restored to "
            f"{source_path}: {history_error}"
        ) from history_error
    return destination_path


def organize_folder(
    source_dir,
    on_organized: Callable[[Path, Path], None] | None = None,
):
    source_path = Path(source_dir)
    if not source_path.is_dir():
        return False, "Directory does not exist!"

    moved_count = 0
    action_id = uuid.uuid4().hex
    custom_rules = load_custom_rules()
    for item_path in source_path.iterdir():
        if item_path.is_symlink() or not item_path.is_file():
            continue
        destination = organize_file(item_path, custom_rules, action_id)
        moved_count += 1
        if on_organized is not None:
            on_organized(item_path, destination)

    message = f"Successfully organized {moved_count} files!"
    return True, message