"""自定义控件"""
from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QPushButton, QHBoxLayout,
    QListWidget, QListWidgetItem, QWidget,
)


class DropArea(QFrame):
    """文件拖拽区域"""
    files_dropped = pyqtSignal(list)  # 发送文件路径列表

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.icon_label = QLabel("📄")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet("font-size: 48px;")
        layout.addWidget(self.icon_label)

        self.hint_label = QLabel()
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint_label.setStyleSheet("font-size: 14px; color: #666;")
        layout.addWidget(self.hint_label)

        self.or_label = QLabel()
        self.or_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.or_label.setStyleSheet("font-size: 12px; color: #999; margin: 4px 0;")
        layout.addWidget(self.or_label)

        self.select_btn = QPushButton()
        self.select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_btn.setStyleSheet("""
            QPushButton {
                background-color: #4A90D9;
                color: white;
                border: none;
                padding: 8px 24px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #357ABD; }
            QPushButton:pressed { background-color: #2A6099; }
        """)
        layout.addWidget(self.select_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self.set_fixed_style()

    def set_fixed_style(self):
        self.setFrameStyle(QFrame.Shape.StyledPanel)
        self.setStyleSheet("""
            DropArea {
                border: 2px dashed #ccc;
                border-radius: 8px;
                background-color: #fafafa;
                min-height: 160px;
            }
            DropArea[dragOver=true] {
                border-color: #4A90D9;
                background-color: #EBF5FF;
            }
        """)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(url.toLocalFile().lower().endswith(".pdf") for url in urls):
                event.acceptProposedAction()
                self.setProperty("dragOver", True)
                self.style().unpolish(self)
                self.style().polish(self)

    def dragLeaveEvent(self, event):
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event: QDropEvent):
        self.setProperty("dragOver", False)
        self.style().unpolish(self)
        self.style().polish(self)

        files = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(".pdf"):
                files.append(path)
        if files:
            self.files_dropped.emit(files)


class FileListWidget(QWidget):
    """文件列表控件"""
    files_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._files: list[str] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 按钮行
        btn_layout = QHBoxLayout()
        self.add_btn = QPushButton()
        self.remove_btn = QPushButton()
        self.clear_btn = QPushButton()

        for btn in [self.add_btn, self.remove_btn, self.clear_btn]:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #f0f0f0;
                    border: 1px solid #ddd;
                    padding: 4px 12px;
                    border-radius: 3px;
                    font-size: 12px;
                }
                QPushButton:hover { background-color: #e0e0e0; }
            """)
            btn_layout.addWidget(btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 文件列表
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                background: white;
                font-size: 12px;
            }
            QListWidget::item { padding: 4px; }
            QListWidget::item:selected { background-color: #4A90D9; color: white; }
        """)
        layout.addWidget(self.list_widget)

        self.remove_btn.clicked.connect(self._remove_selected)
        self.clear_btn.clicked.connect(self._clear_all)

    def add_files(self, files: list[str]):
        for f in files:
            if f not in self._files:
                self._files.append(f)
                item = QListWidgetItem(Path(f).name)
                item.setData(Qt.ItemDataRole.UserRole, f)
                item.setToolTip(f)
                self.list_widget.addItem(item)
        self.files_changed.emit()

    def _remove_selected(self):
        for item in self.list_widget.selectedItems():
            path = item.data(Qt.ItemDataRole.UserRole)
            if path in self._files:
                self._files.remove(path)
            self.list_widget.takeItem(self.list_widget.row(item))
        self.files_changed.emit()

    def _clear_all(self):
        self._files.clear()
        self.list_widget.clear()
        self.files_changed.emit()

    @property
    def files(self) -> list[str]:
        return self._files.copy()
