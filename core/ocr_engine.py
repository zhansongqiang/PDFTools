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

    def is_chart_image(self, image_data: bytes | np.ndarray,
                       img_width: float = 0, img_height: float = 0,
                       page_width: float = 0, page_height: float = 0) -> bool:
        """判断图片是否为图表而非扫描文档

        图表特征：面积占页面 < 50%（柱状图、饼图等嵌入式图表）
        扫描文档特征：面积接近整页（> 80%）
        """
        # 基于面积占比判断（最可靠的指标）
        if img_width > 0 and img_height > 0 and page_width > 0 and page_height > 0:
            area_ratio = (img_width * img_height) / (page_width * page_height)
            # 面积 < 50% 的基本都是嵌入式图表/图片，不需要 OCR
            if area_ratio < 0.5:
                return True
            # 面积 > 80% 的基本都是扫描页面，需要 OCR
            if area_ratio > 0.8:
                return False

        return False

    def is_available(self) -> bool:
        """检查 PaddleOCR 是否可用"""
        try:
            from paddleocr import PaddleOCR  # noqa: F401
            return True
        except ImportError:
            return False
