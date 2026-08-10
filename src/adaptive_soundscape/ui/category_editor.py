"""Dialog for configuring process/title names per work context category."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from adaptive_soundscape.context.user_mappings import (
    CONFIGURABLE_CONTEXTS,
    CategoryMapping,
    UserMappings,
)
from adaptive_soundscape.core.events import WorkContext


EDITOR_STYLE = """
QDialog, QWidget {
    background-color: #1a1a1e;
    color: #e8e8ec;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}
QTabWidget::pane {
    border: 1px solid #33333a;
    border-radius: 6px;
    background: #25252b;
}
QTabBar::tab {
    background: #2e2e36;
    color: #c8c8d0;
    padding: 8px 12px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}
QTabBar::tab:selected {
    background: #3a5a8c;
    color: #ffffff;
}
QListWidget {
    background: #1a1a1e;
    border: 1px solid #44444d;
    border-radius: 4px;
}
QLineEdit {
    background: #1a1a1e;
    border: 1px solid #44444d;
    border-radius: 4px;
    padding: 4px 8px;
}
QPushButton {
    background-color: #33333a;
    border: 1px solid #44444d;
    border-radius: 6px;
    padding: 6px 12px;
}
QPushButton:hover { background-color: #3d3d46; }
QLabel#sectionLabel {
    color: #888894;
    font-size: 11px;
    font-weight: 600;
}
"""


def _label_for(ctx: WorkContext) -> str:
    return ctx.value.replace("_", " ").title()


class _CategoryTab(QWidget):
    def __init__(self, mapping: CategoryMapping, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(self._section("Process names (e.g. zed, warp)"))
        self._process_list = QListWidget()
        for name in mapping.process_names:
            self._process_list.addItem(name)
        layout.addWidget(self._process_list)
        self._process_input = QLineEdit()
        self._process_input.setPlaceholderText("Add process name…")
        process_row = QHBoxLayout()
        process_row.addWidget(self._process_input, stretch=1)
        add_proc = QPushButton("Add")
        remove_proc = QPushButton("Remove")
        process_row.addWidget(add_proc)
        process_row.addWidget(remove_proc)
        layout.addLayout(process_row)

        layout.addWidget(self._section("Title keywords (substring match)"))
        self._title_list = QListWidget()
        for keyword in mapping.title_keywords:
            self._title_list.addItem(keyword)
        layout.addWidget(self._title_list)
        self._title_input = QLineEdit()
        self._title_input.setPlaceholderText("Add title keyword…")
        title_row = QHBoxLayout()
        title_row.addWidget(self._title_input, stretch=1)
        add_title = QPushButton("Add")
        remove_title = QPushButton("Remove")
        title_row.addWidget(add_title)
        title_row.addWidget(remove_title)
        layout.addLayout(title_row)

        add_proc.clicked.connect(lambda: self._add(self._process_input, self._process_list))
        remove_proc.clicked.connect(lambda: self._remove(self._process_list))
        add_title.clicked.connect(lambda: self._add(self._title_input, self._title_list))
        remove_title.clicked.connect(lambda: self._remove(self._title_list))
        self._process_input.returnPressed.connect(
            lambda: self._add(self._process_input, self._process_list)
        )
        self._title_input.returnPressed.connect(
            lambda: self._add(self._title_input, self._title_list)
        )

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    @staticmethod
    def _add(edit: QLineEdit, listing: QListWidget) -> None:
        text = edit.text().strip().lower()
        if text.endswith(".exe"):
            text = text[:-4]
        if not text:
            return
        existing = {listing.item(i).text() for i in range(listing.count())}
        if text not in existing:
            listing.addItem(text)
        edit.clear()

    @staticmethod
    def _remove(listing: QListWidget) -> None:
        for item in listing.selectedItems():
            listing.takeItem(listing.row(item))

    def to_mapping(self) -> CategoryMapping:
        processes = [
            self._process_list.item(i).text() for i in range(self._process_list.count())
        ]
        titles = [
            self._title_list.item(i).text() for i in range(self._title_list.count())
        ]
        return CategoryMapping(process_names=processes, title_keywords=titles)


class CategoryEditorDialog(QDialog):
    """Edit user-configured names for each WorkContext category."""

    saved = pyqtSignal(object)  # UserMappings

    def __init__(
        self, mappings: UserMappings, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configure Context Categories")
        self.setMinimumSize(520, 480)
        self.setStyleSheet(EDITOR_STYLE)

        root = QVBoxLayout(self)
        intro = QLabel(
            "Add process names or title keywords for each category. "
            "These override built-in rules and skip confirmation prompts."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        self._tabs = QTabWidget()
        self._category_tabs: dict[WorkContext, _CategoryTab] = {}
        for ctx in CONFIGURABLE_CONTEXTS:
            tab = _CategoryTab(mappings.get(ctx))
            self._category_tabs[ctx] = tab
            self._tabs.addTab(tab, _label_for(ctx))
        root.addWidget(self._tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_save(self) -> None:
        mappings = UserMappings()
        for ctx, tab in self._category_tabs.items():
            mapping = tab.to_mapping()
            mappings.set_category(
                ctx,
                process_names=mapping.process_names,
                title_keywords=mapping.title_keywords,
            )
        self.saved.emit(mappings)
        self.accept()

    @staticmethod
    def edit(
        mappings: UserMappings, parent: QWidget | None = None
    ) -> UserMappings | None:
        dialog = CategoryEditorDialog(mappings, parent)
        result_holder: dict[str, UserMappings] = {}

        def _capture(updated: UserMappings) -> None:
            result_holder["mappings"] = updated

        dialog.saved.connect(_capture)
        if dialog.exec() and "mappings" in result_holder:
            return result_holder["mappings"]
        return None
