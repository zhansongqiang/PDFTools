"""OCR 引擎模块 - 封装 PaddleOCR，支持懒加载"""
from __future__ import annotations

from typing import Optional

import numpy as np

from .pdf_parser import image_bytes_to_numpy


class OCREngine:
    """PaddleOCR 封装，懒加载模式"""

    def __init__(self, lang: str = "ch"):
        self._lang = lang
        self._ocr = None

    @property
    def lang(self) -> str:
        return self._lang

    @lang.setter
    def lang(self, value: str):
        if value != self._lang:
            self._lang = value
            self._ocr = None  # 语言变更时重置，下次使用时重新加载

    def _ensure_loaded(self):
        """懒加载 PaddleOCR"""
        if self._ocr is None:
            from paddleocr import PaddleOCR
            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang=self._lang,
            )

    def recognize_image(self, image_data: bytes | np.ndarray) -> str:
        """识别图片中的文字

        Args:
            image_data: 图片字节数据或 numpy 数组

        Returns:
            识别出的文本
        """
        self._ensure_loaded()

        if isinstance(image_data, bytes):
            img_array = image_bytes_to_numpy(image_data)
        else:
            img_array = image_data

        result = self._ocr.ocr(img_array, cls=True)

        if not result or not result[0]:
            return ""

        lines = []
        for line in result[0]:
            if line and len(line) >= 2:
                text = line[1][0] if isinstance(line[1], (list, tuple)) else str(line[1])
                lines.append(text)

        return "\n".join(lines)

    def is_available(self) -> bool:
        """检查 PaddleOCR 是否可用"""
        try:
            from paddleocr import PaddleOCR  # noqa: F401
            return True
        except ImportError:
            return False
