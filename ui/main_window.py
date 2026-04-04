"""主窗口
Copyright (c) 2026 zsq. All rights reserved.
版本: 1.0
联系邮箱: 11016795@qq.com
联系电话: 18820818283
"""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QProgressBar, QFileDialog, QGroupBox, QLineEdit,
    QCheckBox, QComboBox, QMessageBox, QStatusBar,
)
from PyQt6.QtGui import QAction

from utils.i18n import i18n
from core.pdf_parser import parse_pdf
from core.ocr_engine import OCREngine
from core.docx_builder import build_docx
from ui.widgets import DropArea, FileListWidget
from ui.resources import STYLE_SHEET


class ConvertWorker(QThread):
    """后台转换线程 — 支持取消和批量容错"""
    progress = pyqtSignal(int, int)
    file_progress = pyqtSignal(int, int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    file_error = pyqtSignal(str, str)  # filename, error_message

    def __init__(self, files: list[str], output_dir: str,
                 ocr_enabled: bool, ocr_lang: str,
                 ocr_engine: Optional[OCREngine] = None):
        super().__init__()
        self.files = files
        self.output_dir = output_dir
        self.ocr_enabled = ocr_enabled
        self.ocr_lang = ocr_lang
        self._cancelled = False
        self._ocr = ocr_engine  # 复用外部传入的 OCR 引擎

    def cancel(self):
        """请求取消转换"""
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def run(self):
        try:
            if self.ocr_enabled and self._ocr is None:
                self._ocr = OCREngine(lang=self.ocr_lang)
            elif self.ocr_enabled and self._ocr and self._ocr.lang != self.ocr_lang:
                self._ocr.lang = self.ocr_lang

            total_files = len(self.files)
            errors = []

            for file_idx, pdf_path in enumerate(self.files):
                if self._cancelled:
                    break

                self.file_progress.emit(file_idx + 1, total_files)

                try:
                    pages = parse_pdf(pdf_path)

                    if self._cancelled:
                        break

                    # OCR 处理
                    if self._ocr:
                        for page in pages:
                            if self._cancelled:
                                break
                            for img_block in page.image_blocks:
                                try:
                                    if img_block.is_chart_render:
                                        continue
                                    if self._ocr.is_chart_image(
                                        img_block.data,
                                        img_block.width, img_block.height,
                                        page.width, page.height,
                                    ):
                                        continue
                                    img_block.ocr_text = self._ocr.recognize_image(img_block.data)
                                except Exception:
                                    img_block.ocr_text = ""

                    if self._cancelled:
                        break

                    output_name = Path(pdf_path).stem + ".docx"
                    output_path = os.path.join(self.output_dir, output_name)
                    build_docx(pages, output_path, progress_callback=self._on_progress)

                except Exception as e:
                    # 单文件失败不终止，记录错误
                    errors.append(f"{Path(pdf_path).name}: {e}")

            if self._cancelled:
                self.error.emit(i18n.t("convert_cancelled"))
            elif errors:
                error_msg = "\n".join(errors)
                if len(errors) < total_files:
                    # 部分成功
                    self.finished.emit(self.output_dir)
                    self.file_error.emit("", error_msg)
                else:
                    self.error.emit(error_msg)
            else:
                self.finished.emit(self.output_dir)

        except Exception as e:
            self.error.emit(f"{e}\n{traceback.format_exc()}")

    def _on_progress(self, current: int, total: int):
        if not self._cancelled:
            self.progress.emit(current, total)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._worker: Optional[ConvertWorker] = None
        self._ocr_engine: Optional[OCREngine] = None  # OCR 引擎复用
        self._setup_ui()
        self._update_texts()

    def _setup_ui(self):
        self.setMinimumSize(700, 550)
        self.setStyleSheet(STYLE_SHEET)

        # 菜单栏
        menubar = self.menuBar()
        lang_menu = menubar.addMenu("")

        self._zh_action = QAction("中文", self)
        self._en_action = QAction("English", self)
        self._zh_action.triggered.connect(lambda: self._switch_lang("zh"))
        self._en_action.triggered.connect(lambda: self._switch_lang("en"))
        lang_menu.addAction(self._zh_action)
        lang_menu.addAction(self._en_action)

        self._about_action = QAction("", self)
        self._about_action.triggered.connect(self._show_about)
        help_menu = menubar.addMenu("")
        help_menu.addAction(self._about_action)

        # 中央控件
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # 拖拽区域
        self.drop_area = DropArea()
        self.drop_area.select_btn.clicked.connect(self._select_files)
        self.drop_area.files_dropped.connect(self._on_files_dropped)
        main_layout.addWidget(self.drop_area)

        # 文件列表
        self.file_list_group = QGroupBox()
        fl_layout = QVBoxLayout(self.file_list_group)
        self.file_list = FileListWidget()
        self.file_list.add_btn.clicked.connect(self._select_files)
        fl_layout.addWidget(self.file_list)
        main_layout.addWidget(self.file_list_group)

        # 设置区域
        settings_layout = QHBoxLayout()

        self.ocr_check = QCheckBox()
        settings_layout.addWidget(self.ocr_check)

        settings_layout.addWidget(QLabel(""))
        self.ocr_lang_combo = QComboBox()
        self.ocr_lang_combo.addItem("中文", "ch")
        self.ocr_lang_combo.addItem("English", "en")
        settings_layout.addWidget(self.ocr_lang_combo)
        settings_layout.addStretch()

        main_layout.addLayout(settings_layout)

        # 输出目录
        output_layout = QHBoxLayout()
        self.output_label = QLabel()
        self.output_edit = QLineEdit()
        self.output_edit.setReadOnly(True)
        self.output_btn = QPushButton()
        self.output_btn.clicked.connect(self._select_output_dir)
        output_layout.addWidget(self.output_label)
        output_layout.addWidget(self.output_edit, stretch=1)
        output_layout.addWidget(self.output_btn)
        main_layout.addLayout(output_layout)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        # 按钮：转换 + 取消
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.convert_btn = QPushButton()
        self.convert_btn.setObjectName("convertBtn")
        self.convert_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.convert_btn.clicked.connect(self._start_convert)
        btn_layout.addWidget(self.convert_btn)

        self.cancel_btn = QPushButton()
        self.cancel_btn.setObjectName("cancelBtn")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self._cancel_convert)
        self.cancel_btn.hide()  # 默认隐藏
        btn_layout.addWidget(self.cancel_btn)

        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

        # 状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def _switch_lang(self, lang: str):
        i18n.lang = lang
        self._update_texts()

    def _update_texts(self):
        """更新所有界面文本"""
        self.setWindowTitle(i18n.t("app_title"))

        self.menuBar().actions()[0].setText(i18n.t("language"))
        self.menuBar().actions()[1].setText(i18n.t("about"))

        self.drop_area.hint_label.setText(i18n.t("drag_hint"))
        self.drop_area.or_label.setText(i18n.t("or"))
        self.drop_area.select_btn.setText(i18n.t("click_select"))

        self.file_list_group.setTitle(i18n.t("file_list"))
        self.file_list.add_btn.setText(i18n.t("add_files"))
        self.file_list.remove_btn.setText(i18n.t("remove_files"))
        self.file_list.clear_btn.setText(i18n.t("clear_files"))

        self.ocr_check.setText(i18n.t("enable_ocr"))

        self.output_label.setText(i18n.t("output_path"))
        self.output_btn.setText(i18n.t("select_output"))

        self.convert_btn.setText(i18n.t("convert"))
        self.cancel_btn.setText(i18n.t("cancel"))

        self.status_bar.showMessage(i18n.t("status_ready"))

    def _select_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, i18n.t("select_files"), "",
            "PDF Files (*.pdf);;All Files (*)"
        )
        if files:
            self._on_files_dropped(files)

    def _on_files_dropped(self, files: list[str]):
        self.file_list.add_files(files)
        if files and not self.output_edit.text():
            self.output_edit.setText(str(Path(files[0]).parent))

    def _select_output_dir(self):
        d = QFileDialog.getExistingDirectory(self, i18n.t("select_output"))
        if d:
            self.output_edit.setText(d)

    def _start_convert(self):
        files = self.file_list.files
        if not files:
            QMessageBox.warning(self, "", i18n.t("no_files"))
            return

        output_dir = self.output_edit.text()
        if not output_dir:
            QMessageBox.warning(self, "", i18n.t("no_output"))
            return

        os.makedirs(output_dir, exist_ok=True)

        ocr_enabled = self.ocr_check.isChecked()
        ocr_lang = self.ocr_lang_combo.currentData() or "ch"

        # 显示取消按钮，隐藏转换按钮
        self.convert_btn.hide()
        self.cancel_btn.show()
        self.progress_bar.setValue(0)
        self.status_bar.showMessage(i18n.t("status_processing"))

        self._worker = ConvertWorker(
            files, output_dir, ocr_enabled, ocr_lang,
            ocr_engine=self._ocr_engine,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.file_progress.connect(self._on_file_progress)
        self._worker.finished.connect(self._on_convert_finished)
        self._worker.error.connect(self._on_convert_error)
        self._worker.file_error.connect(self._on_file_errors)
        self._worker.start()

    def _cancel_convert(self):
        """取消转换"""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.status_bar.showMessage(i18n.t("cancelling"))

    def _on_progress(self, current: int, total: int):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_bar.showMessage(i18n.t("processing_page", current=current, total=total))

    def _on_file_progress(self, file_idx: int, total: int):
        pass

    def _on_convert_finished(self, output_dir: str):
        self.convert_btn.show()
        self.cancel_btn.hide()
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.status_bar.showMessage(i18n.t("convert_success"))

        QMessageBox.information(self, i18n.t("convert_success"), i18n.t("convert_success"))

        try:
            if sys.platform == "win32":
                os.startfile(output_dir)
            elif sys.platform == "darwin":
                os.system(f"open '{output_dir}'")
            else:
                os.system(f"xdg-open '{output_dir}'")
        except Exception:
            pass

    def _on_convert_error(self, msg: str):
        self.convert_btn.show()
        self.cancel_btn.hide()
        self.status_bar.showMessage(i18n.t("convert_failed"))
        QMessageBox.critical(self, i18n.t("convert_failed"), msg)

    def _on_file_errors(self, _, error_msg: str):
        """部分文件转换失败的警告"""
        QMessageBox.warning(
            self,
            i18n.t("partial_error"),
            f"{i18n.t('some_files_failed')}:\n{error_msg}"
        )

    def _show_about(self):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
        dlg = QDialog(self)
        dlg.setWindowTitle(i18n.t("about"))
        dlg.setFixedSize(360, 260)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(8)

        title = QLabel("PDF 转 Word 工具 v1.0")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 10px;")
        layout.addWidget(title)

        info = QLabel(
            "Copyright © 2026 zsq\n"
            "All rights reserved.\n\n"
            "联系邮箱：11016795@qq.com\n"
            "联系电话：18820818283"
        )
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info.setStyleSheet("font-size: 13px; line-height: 1.6;")
        layout.addWidget(info)

        ok_btn = QPushButton("OK")
        ok_btn.setFixedWidth(80)
        ok_btn.clicked.connect(dlg.accept)
        layout.addWidget(ok_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        dlg.exec()
