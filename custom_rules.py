from __future__ import annotations

import json
import os
import platform
import re
import tempfile
from pathlib import Path


_EXTENSION_PATTERN = re.compile(r"^\.[A-Za-z0-9][A-Za-z0-9_-]*$")
_INVALID_CATEGORY_CHARACTERS = set('<>:"/\\|?*')
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def rules_file_path() -> Path:
    if platform.system() == "Windows":
        base_directory = Path(
            os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")
        )
    else:
        base_directory = Path(
            os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        )
    return base_directory / "SmartFileOrganizer" / "custom_rules.json"


def validate_rule(extension: str, category: str) -> tuple[str, str]:
    normalized_extension = extension.strip().lower()
    normalized_category = category.strip()
    if not _EXTENSION_PATTERN.fullmatch(normalized_extension):
        raise ValueError("Extension must look like .pdf or .zip.")
    if (
        not normalized_category
        or normalized_category in {".", ".."}
        or normalized_category.casefold() == ".private_vault"
        or normalized_category.endswith((".", " "))
        or any(character in _INVALID_CATEGORY_CHARACTERS for character in normalized_category)
        or any(ord(character) < 32 for character in normalized_category)
        or normalized_category.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES
    ):
        raise ValueError("Enter a valid folder name for the category.")
    return normalized_extension, normalized_category


def load_custom_rules() -> dict[str, str]:
    path = rules_file_path()
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as error:
        raise OSError(f"Could not read custom rules from {path}: {error}") from error

    try:
        document = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError(f"Custom rules JSON is invalid: {path} ({error})") from error

    if not isinstance(document, dict) or document.get("version") != 1:
        raise ValueError(f"Unsupported custom rules format: {path}")
    raw_rules = document.get("rules")
    if not isinstance(raw_rules, list):
        raise ValueError(f"Custom rules must contain a rules list: {path}")

    rules: dict[str, str] = {}
    for index, entry in enumerate(raw_rules):
        if not isinstance(entry, dict):
            raise ValueError(f"Custom rule #{index + 1} must be an object.")
        extension = entry.get("extension")
        category = entry.get("category")
        if not isinstance(extension, str) or not isinstance(category, str):
            raise ValueError(f"Custom rule #{index + 1} needs string extension and category.")
        normalized_extension, normalized_category = validate_rule(extension, category)
        if normalized_extension in rules:
            raise ValueError(f"Duplicate custom rule for {normalized_extension}.")
        rules[normalized_extension] = normalized_category
    return rules


def save_custom_rules(rules: dict[str, str]) -> Path:
    normalized_rules: dict[str, str] = {}
    for extension, category in rules.items():
        normalized_extension, normalized_category = validate_rule(extension, category)
        if normalized_extension in normalized_rules:
            raise ValueError(f"Duplicate custom rule for {normalized_extension}.")
        normalized_rules[normalized_extension] = normalized_category

    path = rules_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "version": 1,
        "rules": [
            {"extension": extension, "category": category}
            for extension, category in sorted(normalized_rules.items())
        ],
    }

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(document, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
        os.replace(temporary_path, path)
    except OSError as error:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise OSError(f"Could not save custom rules to {path}: {error}") from error
    return path
