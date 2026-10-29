import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QGraphicsDropShadowEffect,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QInputDialog,
    QPushButton,
    QLabel,
    QFileDialog,
    QMessageBox,
)
from PyQt6.QtCore import QRect, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from activity_log import (
    activity_summary,
    latest_undoable_action,
    recent_activity,
    undo_latest_action,
)
from cleaner import CleanupCandidate, ScanResult, move_to_trash, scan_folder
from custom_rules import (
    load_custom_rules,
    rules_file_path,
    save_custom_rules,
    validate_rule,
)
from image_watcher import AutoImageSorter
from organizer import organize_folder
from organizer_watcher import LiveFolderOrganizer
from vault import (
    VaultEntry,
    hide_in_vault,
    list_folder_entries,
    list_vault_entries,
    restore_from_vault,
)


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


class StorageRing(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.percent = 0
        self.setMinimumSize(120, 120)

    def set_percent(self, percent: int) -> None:
        self.percent = max(0, min(percent, 100))
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = min(self.width(), self.height()) - 18
        rect = self.rect().adjusted(
            (self.width() - side) // 2,
            (self.height() - side) // 2,
            -(self.width() - side) // 2,
            -(self.height() - side) // 2,
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#334155"), 10))
        painter.drawEllipse(rect)
        painter.setPen(
            QPen(
                QColor("#34d399"),
                10,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        painter.drawArc(rect, 90 * 16, -int(self.percent * 360 / 100) * 16)
        painter.setPen(QColor("#f8fafc"))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, f"{self.percent}%")


class CategoryBarChart(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.category_counts: dict[str, int] = {}
        self.setMinimumHeight(190)

    def set_category_counts(self, category_counts: dict[str, int]) -> None:
        self.category_counts = category_counts
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.category_counts:
            painter.setPen(QColor("#94a3b8"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No organized files yet")
            return

        entries = list(self.category_counts.items())
        max_count = max(count for _, count in entries) or 1
        label_width = 120
        value_width = 48
        top = 12
        row_height = max(25, min(38, (self.height() - 24) // len(entries)))
        bar_left = label_width
        bar_width = max(40, self.width() - label_width - value_width - 20)
        for index, (category, count) in enumerate(entries):
            y = top + index * row_height
            painter.setPen(QColor("#cbd5e1"))
            painter.drawText(
                0,
                y,
                label_width - 8,
                row_height,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                category,
            )
            track = QRect(bar_left, y + 6, bar_width, row_height - 12)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#334155"))
            painter.drawRoundedRect(track, 5, 5)
            fill = track
            fill.setWidth(max(5, int(bar_width * count / max_count)))
            painter.setBrush(QColor("#818cf8"))
            painter.drawRoundedRect(fill, 5, 5)
            painter.setPen(QColor("#f8fafc"))
            painter.drawText(
                bar_left + bar_width + 8,
                y,
                value_width,
                row_height,
                Qt.AlignmentFlag.AlignVCenter,
                str(count),
            )


class FolderScanWorker(QThread):
    scan_completed = pyqtSignal(object)
    scan_failed = pyqtSignal(str)

    def __init__(self, folder: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.folder = folder

    def run(self) -> None:
        try:
            self.scan_completed.emit(scan_folder(self.folder))
        except (OSError, ValueError) as error:
            self.scan_failed.emit(str(error))


class CleanerDialog(QDialog):
    def __init__(self, folder: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.folder = folder
        self.scan_result: ScanResult | None = None
        self.worker: FolderScanWorker | None = None
        self.setWindowTitle("Smart Duplicate & Junk Cleaner")
        self.setMinimumSize(720, 520)
        self._build_ui()
        self._start_scan()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        summary = QVBoxLayout()
        title = QLabel("Storage cleanup")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #c4b5fd;")
        summary.addWidget(title)
        summary.addWidget(
            QLabel("Review duplicate copies and likely temporary files before sending them to Trash.")
        )
        self.status_label = QLabel("Scanning selected folder...")
        self.status_label.setWordWrap(True)
        summary.addWidget(self.status_label)
        header.addLayout(summary, 1)

        ring_layout = QVBoxLayout()
        self.storage_ring = StorageRing()
        ring_layout.addWidget(self.storage_ring, alignment=Qt.AlignmentFlag.AlignCenter)
        self.ring_label = QLabel("Potential space\n0 B")
        self.ring_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ring_layout.addWidget(self.ring_label)
        header.addLayout(ring_layout)
        layout.addLayout(header)

        self.candidate_tree = QTreeWidget()
        self.candidate_tree.setColumnCount(3)
        self.candidate_tree.setHeaderLabels(["File", "Reason", "Size"])
        self.candidate_tree.setColumnWidth(0, 390)
        self.candidate_tree.setColumnWidth(1, 150)
        layout.addWidget(self.candidate_tree, 1)

        controls = QHBoxLayout()
        self.select_all_button = QPushButton("Select all")
        self.select_all_button.clicked.connect(lambda: self._set_all_checked(True))
        controls.addWidget(self.select_all_button)
        self.clear_selection_button = QPushButton("Clear selection")
        self.clear_selection_button.clicked.connect(lambda: self._set_all_checked(False))
        controls.addWidget(self.clear_selection_button)
        controls.addStretch()
        self.clean_button = QPushButton("Move selected to Trash")
        self.clean_button.setObjectName("organizeBtn")
        self.clean_button.clicked.connect(self._clean_selected)
        controls.addWidget(self.clean_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        controls.addWidget(close_button)
        layout.addLayout(controls)

    def _start_scan(self) -> None:
        self.status_label.setText("Scanning selected folder and hashing same-size files...")
        self.clean_button.setEnabled(False)
        self.worker = FolderScanWorker(self.folder, self)
        self.worker.scan_completed.connect(self._show_scan_results)
        self.worker.scan_failed.connect(self._show_scan_error)
        self.worker.start()

    def _show_scan_results(self, result: ScanResult) -> None:
        self.scan_result = result
        self.candidate_tree.clear()
        for candidate in result.candidates:
            item = QTreeWidgetItem(
                [str(candidate.path), candidate.reason, format_size(candidate.size)]
            )
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked)
            item.setData(0, Qt.ItemDataRole.UserRole, candidate)
            self.candidate_tree.addTopLevelItem(item)

        percentage = (
            round(result.reclaimable_size * 100 / result.total_size)
            if result.total_size
            else 0
        )
        self.storage_ring.set_percent(percentage)
        self.ring_label.setText(
            f"Potential space\n{format_size(result.reclaimable_size)}"
        )
        self.clean_button.setEnabled(bool(result.candidates))
        self.status_label.setText(
            f"Scanned {format_size(result.total_size)}. "
            f"Found {len(result.candidates)} candidate file(s). "
            "Candidates are selected by default; review them before cleanup."
        )
        if result.errors:
            details = "\n".join(result.errors[:5])
            if len(result.errors) > 5:
                details += f"\n...and {len(result.errors) - 5} more."
            QMessageBox.warning(
                self,
                "Some files could not be scanned",
                f"{len(result.errors)} scan error(s):\n\n{details}",
            )

    def _show_scan_error(self, message: str) -> None:
        self.status_label.setText("Scan failed.")
        QMessageBox.critical(self, "Scan failed", message)

    def _set_all_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for index in range(self.candidate_tree.topLevelItemCount()):
            item = self.candidate_tree.topLevelItem(index)
            if item is not None:
                item.setCheckState(0, state)

    def _clean_selected(self) -> None:
        selected: list[CleanupCandidate] = []
        for index in range(self.candidate_tree.topLevelItemCount()):
            item = self.candidate_tree.topLevelItem(index)
            if item is None:
                continue
            if item.checkState(0) == Qt.CheckState.Checked:
                candidate = item.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(candidate, CleanupCandidate):
                    selected.append(candidate)

        if not selected:
            QMessageBox.information(self, "Nothing selected", "Select files to move to Trash.")
            return

        total_size = sum(candidate.size for candidate in selected)
        answer = QMessageBox.question(
            self,
            "Confirm cleanup",
            f"Move {len(selected)} selected file(s) ({format_size(total_size)}) "
            "to the system Trash/Recycle Bin?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        result = move_to_trash(selected)
        message = (
            f"Moved {len(result.moved)} file(s) to Trash "
            f"({format_size(result.reclaimed_size)})."
        )
        if result.errors:
            details = "\n".join(result.errors[:5])
            if len(result.errors) > 5:
                details += f"\n...and {len(result.errors) - 5} more."
            QMessageBox.warning(
                self,
                "Cleanup completed with errors",
                f"{message}\n{len(result.errors)} file(s) could not be moved:\n\n{details}",
            )
        else:
            QMessageBox.information(self, "Cleanup complete", message)
        self._start_scan()

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.isRunning():
            self.status_label.setText("Please wait for the folder scan to finish before closing.")
            event.ignore()
            return
        super().closeEvent(event)


class VaultDialog(QDialog):
    def __init__(self, folder: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.folder = folder
        self.setWindowTitle("Private Vault (hidden folder)")
        self.setMinimumSize(760, 520)
        self._build_ui()
        self._refresh_entries()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("Private Vault")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #c4b5fd;")
        layout.addWidget(title)

        warning = QLabel(
            "Hidden-folder mode only: this does not encrypt or password-protect files. "
            "Anyone with access to the folder can reveal and open the vault."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "color: #fde68a; background-color: rgba(245, 158, 11, 35); "
            "border: 1px solid rgba(245, 158, 11, 100); border-radius: 8px; padding: 10px;"
        )
        layout.addWidget(warning)

        columns = QHBoxLayout()
        available_layout = QVBoxLayout()
        available_layout.addWidget(QLabel("Selected folder"))
        self.available_tree = QTreeWidget()
        self.available_tree.setHeaderLabels(["File or folder"])
        available_layout.addWidget(self.available_tree)
        columns.addLayout(available_layout)

        vault_layout = QVBoxLayout()
        vault_layout.addWidget(QLabel("Hidden vault"))
        self.vault_tree = QTreeWidget()
        self.vault_tree.setHeaderLabels(["Vault item"])
        vault_layout.addWidget(self.vault_tree)
        columns.addLayout(vault_layout)
        layout.addLayout(columns, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        buttons = QHBoxLayout()
        self.hide_button = QPushButton("Move selected into vault")
        self.hide_button.clicked.connect(self._hide_selected)
        buttons.addWidget(self.hide_button)
        self.restore_button = QPushButton("Restore selected")
        self.restore_button.clicked.connect(self._restore_selected)
        buttons.addWidget(self.restore_button)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._refresh_entries)
        buttons.addWidget(refresh_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    @staticmethod
    def _populate_tree(tree: QTreeWidget, entries: list[VaultEntry]) -> None:
        tree.clear()
        for entry in entries:
            label = f"{entry.path.name}{'  [folder]' if entry.is_directory else ''}"
            item = QTreeWidgetItem([label])
            item.setToolTip(0, str(entry.path))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setData(0, Qt.ItemDataRole.UserRole, entry)
            tree.addTopLevelItem(item)

    @staticmethod
    def _selected_names(tree: QTreeWidget) -> list[str]:
        names = []
        for index in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(index)
            if item is None or item.checkState(0) != Qt.CheckState.Checked:
                continue
            entry = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(entry, VaultEntry):
                names.append(entry.path.name)
        return names

    def _refresh_entries(self) -> None:
        try:
            self._populate_tree(self.available_tree, list_folder_entries(self.folder))
            self._populate_tree(self.vault_tree, list_vault_entries(self.folder))
            self.status_label.setText(
                f"Vault location: {self.folder} / .private_vault"
            )
        except (OSError, ValueError) as error:
            self.status_label.setText(f"Could not read vault contents: {error}")
            QMessageBox.critical(self, "Vault error", str(error))

    def _hide_selected(self) -> None:
        names = self._selected_names(self.available_tree)
        if not names:
            QMessageBox.information(self, "Nothing selected", "Select files or folders to move.")
            return

        answer = QMessageBox.question(
            self,
            "Move items into hidden folder?",
            f"Move {len(names)} item(s) into the hidden vault? "
            "This only hides the folder; it does not encrypt the contents.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            result = hide_in_vault(self.folder, names)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Could not move items", str(error))
            return
        self._show_operation_result("Moved into vault", result.moved, result.errors)

    def _restore_selected(self) -> None:
        names = self._selected_names(self.vault_tree)
        if not names:
            QMessageBox.information(self, "Nothing selected", "Select vault items to restore.")
            return

        answer = QMessageBox.question(
            self,
            "Restore selected items?",
            f"Move {len(names)} item(s) out of the hidden vault? "
            "If a name already exists, a numbered name will be used.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        result = restore_from_vault(self.folder, names)
        self._show_operation_result("Restored from vault", result.moved, result.errors)

    def _show_operation_result(
        self, action: str, moved: list[Path], errors: list[str]
    ) -> None:
        message = f"{action}: {len(moved)} item(s)."
        self._refresh_entries()
        self.status_label.setText(message)
        if errors:
            details = "\n".join(errors[:5])
            if len(errors) > 5:
                details += f"\n...and {len(errors) - 5} more."
            QMessageBox.warning(
                self,
                "Vault operation completed with errors",
                f"{message}\n\n{details}",
            )


class CustomRulesDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Custom Extension Rules")
        self.setMinimumSize(520, 400)
        self.rules: dict[str, str] = {}
        self._build_ui()
        self._load_rules()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("Custom extension rules")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #c4b5fd;")
        layout.addWidget(title)
        description = QLabel(
            "Custom rules override built-in categories and are used by both "
            "Organize Now and live file organization."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self.rules_tree = QTreeWidget()
        self.rules_tree.setHeaderLabels(["Extension", "Destination category"])
        self.rules_tree.setColumnWidth(0, 130)
        layout.addWidget(self.rules_tree, 1)

        self.location_label = QLabel(f"Saved locally in: {rules_file_path()}")
        self.location_label.setWordWrap(True)
        self.location_label.setStyleSheet("color: #94a3b8; font-size: 11px;")
        layout.addWidget(self.location_label)

        controls = QHBoxLayout()
        self.add_rule_button = QPushButton("Add / update rule")
        self.add_rule_button.clicked.connect(self._add_rule)
        controls.addWidget(self.add_rule_button)
        self.remove_rule_button = QPushButton("Remove selected")
        self.remove_rule_button.clicked.connect(self._remove_selected)
        controls.addWidget(self.remove_rule_button)
        controls.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        controls.addWidget(close_button)
        layout.addLayout(controls)

    def _load_rules(self) -> None:
        try:
            self.rules = load_custom_rules()
        except (OSError, ValueError) as error:
            self.rules = {}
            self.rules_tree.clear()
            QMessageBox.critical(self, "Could not load custom rules", str(error))
            self.add_rule_button.setEnabled(False)
            self.remove_rule_button.setEnabled(False)
            return

        self.rules_tree.clear()
        for extension, category in sorted(self.rules.items()):
            item = QTreeWidgetItem([extension, category])
            self.rules_tree.addTopLevelItem(item)

    def _add_rule(self) -> None:
        extension, accepted = QInputDialog.getText(
            self,
            "Rule extension",
            "File extension (example: .pdf):",
        )
        if not accepted:
            return
        category, accepted = QInputDialog.getText(
            self,
            "Rule category",
            "Destination folder name (example: E-Books):",
        )
        if not accepted:
            return

        try:
            normalized_extension, normalized_category = validate_rule(
                extension, category
            )
        except ValueError as error:
            QMessageBox.warning(self, "Invalid custom rule", str(error))
            return

        if normalized_extension in self.rules:
            answer = QMessageBox.question(
                self,
                "Update existing rule?",
                f"A custom rule for {normalized_extension} already exists. Replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return

        updated_rules = dict(self.rules)
        updated_rules[normalized_extension] = normalized_category
        try:
            save_custom_rules(updated_rules)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Could not save custom rule", str(error))
            return
        self._load_rules()

    def _remove_selected(self) -> None:
        item = self.rules_tree.currentItem()
        if item is None:
            QMessageBox.information(self, "No rule selected", "Select a rule to remove.")
            return
        extension = item.text(0)
        updated_rules = dict(self.rules)
        updated_rules.pop(extension, None)
        try:
            save_custom_rules(updated_rules)
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Could not remove custom rule", str(error))
            return
        self._load_rules()


class ActivityDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Activity Log & Visual Stats")
        self.setMinimumSize(820, 600)
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("Activity dashboard")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #c4b5fd;")
        layout.addWidget(title)
        self.total_label = QLabel("Total files organized: 0")
        self.total_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.total_label)

        layout.addWidget(QLabel("Files by category"))
        self.category_chart = CategoryBarChart()
        layout.addWidget(self.category_chart)

        layout.addWidget(QLabel("Recent organization history"))
        self.history_tree = QTreeWidget()
        self.history_tree.setColumnCount(4)
        self.history_tree.setHeaderLabels(
            ["Time", "Category", "Original path", "Organized path"]
        )
        self.history_tree.setColumnWidth(0, 155)
        self.history_tree.setColumnWidth(1, 110)
        self.history_tree.setColumnWidth(2, 245)
        layout.addWidget(self.history_tree, 1)

        controls = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        controls.addWidget(self.status_label, 1)
        self.undo_button = QPushButton("Undo latest action")
        self.undo_button.clicked.connect(self._undo_latest)
        controls.addWidget(self.undo_button)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._refresh)
        controls.addWidget(refresh_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)
        controls.addWidget(close_button)
        layout.addLayout(controls)

    def _refresh(self) -> None:
        try:
            total, category_counts = activity_summary()
            history = recent_activity()
            latest_action = latest_undoable_action()
        except (OSError, ValueError) as error:
            self.status_label.setText(f"Could not load activity history: {error}")
            QMessageBox.critical(self, "Activity history error", str(error))
            return

        self.total_label.setText(f"Total files organized: {total}")
        self.category_chart.set_category_counts(category_counts)
        self.history_tree.clear()
        for occurred_at, category, source, destination, undone in history:
            item = QTreeWidgetItem(
                [
                    occurred_at.replace("T", " "),
                    category,
                    source,
                    destination,
                ]
            )
            if undone:
                item.setText(1, f"{category} (undone)")
            item.setToolTip(2, source)
            item.setToolTip(3, destination)
            self.history_tree.addTopLevelItem(item)
        self.undo_button.setEnabled(latest_action is not None)
        if latest_action is None:
            self.undo_button.setText("Nothing to undo")
        else:
            self.undo_button.setText(
                f"Undo latest action ({latest_action[1]} file(s))"
            )
        self.status_label.setText(
            f"Showing the latest {len(history)} entries. History is stored locally."
        )

    def _undo_latest(self) -> None:
        try:
            action = latest_undoable_action()
        except OSError as error:
            QMessageBox.critical(self, "Could not read undo history", str(error))
            return

        if action is None:
            QMessageBox.information(self, "Nothing to undo", "There is no organization action to undo.")
            self._refresh()
            return

        answer = QMessageBox.question(
            self,
            "Undo latest organization action?",
            f"Restore {action[1]} file(s) to their original locations? "
            "Files will not be overwritten; conflicting files will be left in place.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            moved_count, errors = undo_latest_action()
        except OSError as error:
            QMessageBox.critical(self, "Undo failed", str(error))
            return

        self._refresh()
        message = f"Restored {moved_count} file(s) to their original locations."
        if errors:
            details = "\n".join(errors[:5])
            if len(errors) > 5:
                details += f"\n...and {len(errors) - 5} more."
            QMessageBox.warning(
                self,
                "Undo completed with conflicts",
                f"{message}\n\n{details}",
            )
        else:
            QMessageBox.information(self, "Undo complete", message)


class OrganizerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.selected_folder = ""
        self.image_sorter: AutoImageSorter | None = None
        self.folder_organizer: LiveFolderOrganizer | None = None
        self.initUI()
        self._refresh_undo_button()

    def initUI(self):
        self.setWindowTitle("Smart File Organizer")
        self.setMinimumSize(540, 610)
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                            stop:0 #0f172a, stop:1 #1e1b4b);
            }
            QLabel {
                color: #f8fafc;
                font-family: 'Segoe UI', sans-serif;
                font-size: 14px;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                            stop:0 #3b82f6, stop:1 #6366f1);
                color: white;
                font-weight: bold;
                border-radius: 10px;
                padding: 12px;
                font-size: 14px;
                border: 1px solid rgba(255, 255, 255, 45);
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                            stop:0 #2563eb, stop:1 #4f46e5);
                border: 1px solid rgba(191, 219, 254, 180);
            }
            QPushButton:pressed {
                padding-top: 13px;
                padding-bottom: 11px;
            }
            QPushButton#organizeBtn {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                            stop:0 #10b981, stop:1 #059669);
            }
            QPushButton#organizeBtn:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                            stop:0 #059669, stop:1 #047857);
                border: 1px solid rgba(167, 243, 208, 190);
            }
            QLabel#pathCard {
                color: #cbd5e1;
                background-color: rgba(255, 255, 255, 18);
                border: 1px solid rgba(255, 255, 255, 38);
                border-radius: 10px;
                padding: 12px;
            }
            QTreeWidget {
                color: #e2e8f0;
                background-color: rgba(15, 23, 42, 220);
                alternate-background-color: rgba(30, 41, 59, 180);
                border: 1px solid rgba(255, 255, 255, 38);
                border-radius: 8px;
                padding: 5px;
            }
            QHeaderView::section {
                color: #c4b5fd;
                background-color: #1e1b4b;
                padding: 7px;
                border: none;
            }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout()
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        # Title Label
        title_label = QLabel("Smart File & Folder Organizer")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #c4b5fd;"
        )
        layout.addWidget(title_label)

        # Path Label
        self.path_label = QLabel("No folder selected")
        self.path_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.path_label.setObjectName("pathCard")
        self.path_label.setWordWrap(True)
        self._add_shadow(self.path_label, "#818cf8", blur_radius=22)
        layout.addWidget(self.path_label)

        # Buttons Layout
        btn_layout = QHBoxLayout()
        
        self.select_btn = QPushButton("Select Folder")
        self.select_btn.clicked.connect(self.select_folder)
        self._add_shadow(self.select_btn, "#3b82f6")
        btn_layout.addWidget(self.select_btn)

        self.organize_btn = QPushButton("Organize Now")
        self.organize_btn.setObjectName("organizeBtn")
        self.organize_btn.clicked.connect(self.run_organizer)
        self._add_shadow(self.organize_btn, "#10b981")
        btn_layout.addWidget(self.organize_btn)

        layout.addLayout(btn_layout)
        self.clean_btn = QPushButton("Scan for duplicates & junk")
        self.clean_btn.clicked.connect(self.run_cleaner)
        self._add_shadow(self.clean_btn, "#818cf8")
        layout.addWidget(self.clean_btn)
        self.auto_sort_btn = QPushButton("Start auto-sort new images")
        self.auto_sort_btn.clicked.connect(self.toggle_auto_sorter)
        self._add_shadow(self.auto_sort_btn, "#38bdf8")
        layout.addWidget(self.auto_sort_btn)
        self.auto_sort_status = QLabel(
            "Auto-sort watches new images in the selected folder only."
        )
        self.auto_sort_status.setWordWrap(True)
        self.auto_sort_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.auto_sort_status)
        self.live_organize_btn = QPushButton("Start live file organization")
        self.live_organize_btn.clicked.connect(self.toggle_live_organizer)
        self._add_shadow(self.live_organize_btn, "#22d3ee")
        layout.addWidget(self.live_organize_btn)
        self.live_organize_status = QLabel(
            "Automatically organize new files in the selected folder."
        )
        self.live_organize_status.setWordWrap(True)
        self.live_organize_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.live_organize_status)
        self.vault_btn = QPushButton("Private Vault (hidden, not encrypted)")
        self.vault_btn.clicked.connect(self.run_vault)
        self._add_shadow(self.vault_btn, "#c084fc")
        layout.addWidget(self.vault_btn)
        self.custom_rules_btn = QPushButton("Custom extension rules")
        self.custom_rules_btn.clicked.connect(self.run_custom_rules)
        self._add_shadow(self.custom_rules_btn, "#f472b6")
        layout.addWidget(self.custom_rules_btn)
        self.activity_btn = QPushButton("Activity log & stats")
        self.activity_btn.clicked.connect(self.run_activity)
        self._add_shadow(self.activity_btn, "#fbbf24")
        layout.addWidget(self.activity_btn)
        self.undo_btn = QPushButton("Undo last organization action")
        self.undo_btn.clicked.connect(self.undo_last_organization)
        self._add_shadow(self.undo_btn, "#fb7185")
        layout.addWidget(self.undo_btn)
        central_widget.setLayout(layout)

    @staticmethod
    def _add_shadow(widget: QWidget, color: str, blur_radius: float = 18) -> None:
        shadow = QGraphicsDropShadowEffect(widget)
        shadow.setBlurRadius(blur_radius)
        shadow.setColor(QColor(color))
        shadow.setOffset(0, 4)
        widget.setGraphicsEffect(shadow)

    def select_folder(self):
        if self.image_sorter is not None or self.folder_organizer is not None:
            QMessageBox.information(
                self,
                "Stop watchers first",
                "Stop active watchers before changing the selected folder.",
            )
            return
        folder = QFileDialog.getExistingDirectory(self, "Select Directory")
        if folder:
            self.selected_folder = folder
            self.path_label.setText(folder)

    def run_organizer(self):
        if not self.selected_folder:
            QMessageBox.warning(self, "Warning", "Please select a folder first!")
            return

        try:
            success, message = organize_folder(self.selected_folder)
        except (OSError, ValueError) as error:
            self._refresh_undo_button()
            QMessageBox.critical(self, "Could not organize files", str(error))
            return
        if success:
            QMessageBox.information(self, "Success", message)
            self._refresh_undo_button()
        else:
            QMessageBox.critical(self, "Error", message)

    def run_cleaner(self):
        if not self.selected_folder:
            QMessageBox.warning(self, "Warning", "Please select a folder first!")
            return

        dialog = CleanerDialog(self.selected_folder, self)
        dialog.exec()

    def run_vault(self) -> None:
        if not self.selected_folder:
            QMessageBox.warning(self, "Warning", "Please select a folder first!")
            return

        dialog = VaultDialog(self.selected_folder, self)
        dialog.exec()

    def run_custom_rules(self) -> None:
        dialog = CustomRulesDialog(self)
        dialog.exec()

    def run_activity(self) -> None:
        dialog = ActivityDialog(self)
        dialog.exec()
        self._refresh_undo_button()

    def _refresh_undo_button(self) -> None:
        try:
            action = latest_undoable_action()
        except OSError as error:
            self.undo_btn.setEnabled(False)
            self.undo_btn.setText("Undo unavailable")
            self.undo_btn.setToolTip(str(error))
            return
        self.undo_btn.setEnabled(action is not None)
        if action is None:
            self.undo_btn.setText("Nothing to undo")
        else:
            self.undo_btn.setText(
                f"Undo last organization action ({action[1]} file(s))"
            )
        self.undo_btn.setToolTip("")

    def undo_last_organization(self) -> None:
        try:
            action = latest_undoable_action()
        except OSError as error:
            QMessageBox.critical(self, "Could not read undo history", str(error))
            return
        if action is None:
            QMessageBox.information(self, "Nothing to undo", "There is no organization action to undo.")
            self._refresh_undo_button()
            return

        answer = QMessageBox.question(
            self,
            "Undo latest organization action?",
            f"Restore {action[1]} file(s) to their original locations? "
            "Files will not be overwritten; conflicting files will be left in place.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            moved_count, errors = undo_latest_action()
        except OSError as error:
            QMessageBox.critical(self, "Undo failed", str(error))
            return

        self._refresh_undo_button()
        message = f"Restored {moved_count} file(s) to their original locations."
        if errors:
            details = "\n".join(errors[:5])
            if len(errors) > 5:
                details += f"\n...and {len(errors) - 5} more."
            QMessageBox.warning(
                self,
                "Undo completed with conflicts",
                f"{message}\n\n{details}",
            )
        else:
            QMessageBox.information(self, "Undo complete", message)

    def toggle_auto_sorter(self) -> None:
        if self.image_sorter is not None:
            sorter = self.image_sorter
            self.image_sorter = None
            sorter.stop()
            sorter.deleteLater()
            self.auto_sort_btn.setText("Start auto-sort new images")
            self.auto_sort_status.setText("Automatic image sorting is stopped.")
            self.select_btn.setEnabled(True)
            self.organize_btn.setEnabled(True)
            self.clean_btn.setEnabled(True)
            self.live_organize_btn.setEnabled(True)
            self.vault_btn.setEnabled(True)
            return

        if self.folder_organizer is not None:
            QMessageBox.information(
                self,
                "Live organization is active",
                "Stop live file organization before starting the image-only watcher.",
            )
            return

        if not self.selected_folder:
            QMessageBox.warning(self, "Warning", "Please select a folder to watch first!")
            return

        destination = QFileDialog.getExistingDirectory(
            self,
            "Choose destination root (Screenshots_YEAR/date folders will be created inside)",
            self.selected_folder,
        )
        if not destination:
            return

        try:
            sorter = AutoImageSorter(self.selected_folder, destination)
            sorter.image_sorted.connect(self._on_image_sorted)
            sorter.error_occurred.connect(self._on_image_sort_error)
            sorter.start()
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Could not start image watcher", str(error))
            return

        self.image_sorter = sorter
        self.auto_sort_btn.setText("Stop auto-sort")
        self.auto_sort_status.setText(
            "Watching the selected folder for new images. "
            f"Sorted images go to {destination} / Screenshots_YEAR / YYYY-MM-DD."
        )
        self.select_btn.setEnabled(False)
        self.organize_btn.setEnabled(False)
        self.clean_btn.setEnabled(False)
        self.live_organize_btn.setEnabled(False)
        self.vault_btn.setEnabled(False)

    def _on_image_sorted(self, source: str, destination: str) -> None:
        self.auto_sort_status.setText(
            f"Sorted {Path(source).name} to {destination}"
        )
        self._refresh_undo_button()

    def _on_image_sort_error(self, message: str) -> None:
        self.auto_sort_status.setText(f"Auto-sort issue: {message}")

    def toggle_live_organizer(self) -> None:
        if self.folder_organizer is not None:
            organizer = self.folder_organizer
            self.folder_organizer = None
            organizer.stop()
            organizer.deleteLater()
            self.live_organize_btn.setText("Start live file organization")
            self.live_organize_status.setText("Live file organization is stopped.")
            self.select_btn.setEnabled(True)
            self.organize_btn.setEnabled(True)
            self.clean_btn.setEnabled(True)
            self.auto_sort_btn.setEnabled(True)
            self.vault_btn.setEnabled(True)
            return

        if self.image_sorter is not None:
            QMessageBox.information(
                self,
                "Image auto-sort is active",
                "Stop image auto-sort before starting live file organization.",
            )
            return

        if not self.selected_folder:
            QMessageBox.warning(
                self, "Warning", "Please select a folder to watch first!"
            )
            return

        try:
            organizer = LiveFolderOrganizer(self.selected_folder)
            organizer.file_organized.connect(self._on_file_organized)
            organizer.error_occurred.connect(self._on_live_organizer_error)
            organizer.start()
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Could not start folder watcher", str(error))
            return

        self.folder_organizer = organizer
        self.live_organize_btn.setText("Stop live file organization")
        self.live_organize_status.setText(
            "Watching the selected folder for new files. "
            "Files are sorted into category folders after writing finishes."
        )
        self.select_btn.setEnabled(False)
        self.organize_btn.setEnabled(False)
        self.clean_btn.setEnabled(False)
        self.auto_sort_btn.setEnabled(False)
        self.vault_btn.setEnabled(False)

    def _on_file_organized(self, source: str, destination: str) -> None:
        self.live_organize_status.setText(
            f"Organized {Path(source).name} to {destination}"
        )
        self._refresh_undo_button()

    def _on_live_organizer_error(self, message: str) -> None:
        self.live_organize_status.setText(f"Live organizer issue: {message}")

    def closeEvent(self, event) -> None:
        if self.image_sorter is not None:
            self.image_sorter.stop()
            self.image_sorter = None
        if self.folder_organizer is not None:
            self.folder_organizer.stop()
            self.folder_organizer = None
        super().closeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = OrganizerApp()
    window.show()
    sys.exit(app.exec())