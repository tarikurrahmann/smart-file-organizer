from __future__ import annotations

import ctypes
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path


VAULT_DIRECTORY_NAME = ".private_vault"
_FILE_ATTRIBUTE_HIDDEN = 0x2
_INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF


@dataclass(frozen=True)
class VaultEntry:
    path: Path
    is_directory: bool


@dataclass
class VaultOperationResult:
    moved: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _set_hidden(path: Path) -> None:
    if os.name != "nt":
        return

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_attributes = kernel32.GetFileAttributesW
    get_attributes.argtypes = [ctypes.c_wchar_p]
    get_attributes.restype = ctypes.c_uint32
    set_attributes = kernel32.SetFileAttributesW
    set_attributes.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
    set_attributes.restype = ctypes.c_int

    attributes = get_attributes(str(path))
    if attributes == _INVALID_FILE_ATTRIBUTES:
        raise ctypes.WinError(ctypes.get_last_error())
    if not set_attributes(str(path), attributes | _FILE_ATTRIBUTE_HIDDEN):
        raise ctypes.WinError(ctypes.get_last_error())


def _root_directory(folder: str | Path) -> Path:
    root = Path(folder).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"Not a folder: {root}")
    return root


def get_vault_directory(folder: str | Path, create: bool = False) -> Path:
    root = _root_directory(folder)
    vault = root / VAULT_DIRECTORY_NAME
    if vault.exists() and not vault.is_dir():
        raise NotADirectoryError(f"Vault path is not a folder: {vault}")

    if create:
        vault.mkdir(exist_ok=True)
        try:
            _set_hidden(vault)
        except OSError:
            if not any(vault.iterdir()):
                vault.rmdir()
            raise

    return vault


def _is_safe_entry(path: Path) -> bool:
    if path.is_symlink() or path.is_junction():
        return False
    return path.is_file() or path.is_dir()


def list_folder_entries(folder: str | Path) -> list[VaultEntry]:
    root = _root_directory(folder)
    entries = []
    for path in sorted(root.iterdir(), key=lambda item: item.name.casefold()):
        if path.name == VAULT_DIRECTORY_NAME or not _is_safe_entry(path):
            continue
        entries.append(VaultEntry(path=path, is_directory=path.is_dir()))
    return entries


def list_vault_entries(folder: str | Path) -> list[VaultEntry]:
    vault = get_vault_directory(folder)
    if not vault.exists():
        return []
    entries = []
    for path in sorted(vault.iterdir(), key=lambda item: item.name.casefold()):
        if not _is_safe_entry(path):
            continue
        entries.append(VaultEntry(path=path, is_directory=path.is_dir()))
    return entries


def _selected_children(root: Path, selected_names: list[str], vault: Path) -> list[Path]:
    selected = []
    for name in selected_names:
        if not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise ValueError(f"Only direct child names can be moved: {name!r}")
        source = root / name
        if source.parent != root or source == vault or not _is_safe_entry(source):
            raise ValueError(f"Not a movable direct file or folder: {source}")
        selected.append(source)
    return selected


def _available_destination(directory: Path, name: str) -> Path:
    destination = directory / name
    if not destination.exists():
        return destination

    original = Path(name)
    counter = 1
    while True:
        candidate = directory / f"{original.stem} ({counter}){original.suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def hide_in_vault(folder: str | Path, selected_names: list[str]) -> VaultOperationResult:
    root = _root_directory(folder)
    vault = get_vault_directory(root, create=True)
    selected = _selected_children(root, selected_names, vault)
    result = VaultOperationResult()
    for source in selected:
        try:
            shutil.move(str(source), str(_available_destination(vault, source.name)))
            result.moved.append(source)
        except OSError as error:
            result.errors.append(f"{source}: {error}")
    return result


def restore_from_vault(folder: str | Path, selected_names: list[str]) -> VaultOperationResult:
    root = _root_directory(folder)
    vault = get_vault_directory(root)
    result = VaultOperationResult()
    if not vault.is_dir():
        result.errors.append("The vault folder does not exist.")
        return result

    try:
        selected = _selected_children(vault, selected_names, root)
    except ValueError as error:
        result.errors.append(str(error))
        return result

    for source in selected:
        try:
            shutil.move(str(source), str(_available_destination(root, source.name)))
            result.moved.append(source)
        except OSError as error:
            result.errors.append(f"{source}: {error}")
    return result
