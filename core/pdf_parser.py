"""PDF 解析模块 - 使用 PyMuPDF 提取文本、图片、表格
Copyright (c) 2026 zsq. All rights reserved.
版本: 1.0
联系邮箱: 11016795@qq.com
联系电话: 18820818283
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image
import numpy as np


@dataclass
class TextBlock:
    """文本块 - 代表一个完整的段落或标题"""
    text: str
    font_size: float = 12.0
    font_name: str = ""
    bold: bool = False
    italic: bool = False
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0
    # 排版属性
    is_title: bool = False
    title_level: int = 0  # 1=一级标题, 2=二级, 3=三级, 0=正文
    first_line_indent: bool = False  # 首行缩进
    alignment: str = "left"  # left, center, right
    is_page_num: bool = False  # 是否为页码
    is_toc_entry: bool = False  # 是否为目录条目
    # 各 span 的字体信息（用于混合格式）
    spans_info: list = field(default_factory=list)


@dataclass
class ImageBlock:
    """图片块"""
    data: bytes
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0
    ext: str = "png"
    ocr_text: str = ""
    is_chart_render: bool = False  # 是否为矢量图表渲染图


@dataclass
class TableCell:
    """表格单元格"""
    text: str = ""
    bold: bool = False


@dataclass
class TableBlock:
    """表格块"""
    rows: list[list[TableCell]] = field(default_factory=list)
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0
    col_count: int = 0


@dataclass
class PageContent:
    """单页内容"""
    page_num: int
    width: float
    height: float
    text_blocks: list[TextBlock] = field(default_factory=list)
    image_blocks: list[ImageBlock] = field(default_factory=list)
    table_blocks: list[TableBlock] = field(default_factory=list)


def _detect_chart_regions(page, page_width: float, page_height: float) -> list[tuple]:
    """检测页面中的矢量图表区域（基于矢量路径分析）"""
    try:
        drawings = page.get_drawings()
    except Exception:
        return []

    if len(drawings) < 5:
        return []

    # 收集有意义的绘图区域
    rects = []
    has_color_fill = False
    for d in drawings:
        r = d.get("rect")
        if r and r[2] > r[0] + 1 and r[3] > r[1] + 1:
            rects.append(fitz.Rect(r))
        fill = d.get("fill")
        if fill and fill not in ((0, 0, 0), (1, 1, 1), None):
            has_color_fill = True

    if len(rects) < 3:
        return []

    # 计算所有绘图区域的联合边界框
    union = rects[0]
    for r in rects[1:]:
        union |= r

    # 面积占比判断
    chart_area = union.width * union.height
    page_area = page_width * page_height
    area_ratio = chart_area / page_area

    # 判断是否为图表：彩色填充且面积>10%，或面积>25%
    is_chart = (area_ratio > 0.10 and has_color_fill) or area_ratio > 0.25
    if not is_chart:
        return []

    # 渲染用：稍微扩展以包含边缘标签
    margin_side = 30
    render_bbox = (
        max(0, union.x0 - margin_side),
        max(0, union.y0 - margin_side),
        min(page_width, union.x1 + margin_side),
        min(page_height, union.y1 + 15),
    )
    # 文本过滤用：用原始绘图边界（避免误删图表标题）
    filter_bbox = (union.x0 - 5, union.y0 - 5, union.x1 + 5, union.y1 + 5)

    return [(render_bbox, filter_bbox)]


def _render_region_as_image(page, bbox: tuple, dpi: int = 200) -> bytes:
    """将页面指定区域渲染为 PNG 图片"""
    clip = fitz.Rect(bbox)
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, clip=clip)
    return pix.tobytes("png")


def _text_in_chart_region(block: 'TextBlock', filter_bbox: tuple) -> bool:
    """检查文本块是否在图表区域内"""
    tcx = block.x + block.width / 2
    tcy = block.y + block.height / 2
    return (filter_bbox[0] <= tcx <= filter_bbox[2]
            and filter_bbox[1] <= tcy <= filter_bbox[3])


def _is_page_number(text: str, x: float, page_width: float, font_size: float) -> bool:
    """判断是否为页码"""
    text = text.strip()
    if not text:
        return False
    if font_size > 11:
        return False
    # 纯数字，位置在页面底部居中
    if text.isdigit() and abs(x + len(text) * 5 - page_width / 2) < 50:
        return True
    # 小字号纯数字
    if text.isdigit() and font_size <= 10:
        return True
    return False


def _detect_title_level(font_size: float, bold: bool, text: str) -> int:
    """根据字号和格式判断标题级别"""
    if font_size >= 20:
        return 1  # 封面/大标题
    if font_size >= 17:
        return 1  # 一级标题（18pt: 前言, 一、...）
    if font_size >= 14.5:
        return 2  # 二级标题（15.9pt: （一）...）
    if font_size >= 13:
        return 3  # 三级标题（14.1pt: 1.语文）
    return 0


def _extract_tables(page) -> tuple[list[TableBlock], list]:
    """提取表格，返回 (TableBlock列表, 表格边界框列表)"""
    table_blocks = []
    table_bboxes = []

    try:
        table_finder = page.find_tables()
        # PyMuPDF 不同版本 API
        if hasattr(table_finder, 'tables'):
            tables = table_finder.tables
        else:
            # 旧版: TableFinder 本身可迭代
            try:
                tables = list(table_finder)
            except TypeError:
                tables = []

        for table in tables:
            try:
                table_data = table.extract()
            except Exception:
                continue
            if not table_data:
                continue
            rows = []
            for row in table_data:
                cells = []
                for cell in row:
                    cell_text = str(cell or "").strip()
                    cells.append(TableCell(text=cell_text, bold=False))
                rows.append(cells)

            if not rows:
                continue

            bbox = table.bbox
            table_bboxes.append(bbox)
            table_blocks.append(TableBlock(
                rows=rows,
                x=bbox[0], y=bbox[1],
                width=bbox[2] - bbox[0], height=bbox[3] - bbox[1],
                col_count=max(len(r) for r in rows) if rows else 0,
            ))
    except Exception:
        pass

    return table_blocks, table_bboxes


def _is_in_table(bbox: tuple, table_bboxes: list) -> bool:
    """检查 bbox 是否在表格区域内"""
    y_center = (bbox[1] + bbox[3]) / 2
    x_start = bbox[0]
    for tbl_bbox in table_bboxes:
        if (tbl_bbox[1] - 5 <= y_center <= tbl_bbox[3] + 5
                and tbl_bbox[0] - 10 <= x_start <= tbl_bbox[2] + 10):
            return True
    return False


def _merge_spans_to_blocks(lines_data: list, page_width: float, table_bboxes: list = None) -> list[TextBlock]:
    """将 span 级别的数据合并为段落级 TextBlock

    关键策略：
    1. 同一 line 内的所有 span 合并为一个完整文本（解决目录行拆分问题）
    2. 相邻短标题合并（"目"+"录" → "目录"）
    3. 正文不自动合并（保持每行独立，避免破坏目录和排版）
    """
    if table_bboxes is None:
        table_bboxes = []

    blocks = []

    for line_info in lines_data:
        spans = line_info["spans"]
        bbox = line_info["bbox"]

        if not spans:
            continue

        # 检查是否在表格区域内
        if _is_in_table(bbox, table_bboxes):
            continue

        # === 关键改动：合并同一行所有 span ===
        # 不再区分不同 span，而是把同一行的所有文字拼接
        # 这样 "前言..........1" 会被合并为一个完整文本
        full_text = ""
        max_size = 0
        is_bold = False
        is_italic = False
        font_name = ""
        spans_info = []

        for span_text, span_size, span_font, span_bold, span_italic in spans:
            full_text += span_text
            if span_size > max_size:
                max_size = span_size
                font_name = span_font
            if span_bold:
                is_bold = True
            if span_italic:
                is_italic = True
            spans_info.append({
                "text": span_text,
                "size": span_size,
                "bold": span_bold,
                "italic": span_italic,
                "font": span_font,
            })

        text = full_text.strip()
        if not text:
            continue

        # 过滤页码
        if _is_page_number(text, bbox[0], page_width, max_size):
            continue

        # 过滤纯点线（整行只有 "............"）
        clean = text.replace(".", "").replace(" ", "").replace("\u3000", "")
        if clean == "" and "." in text:
            continue

        x = bbox[0]
        y = bbox[1]
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]

        # 检测是否为目录条目（包含大量点号的行）
        is_toc = "..." in text and text.count(".") > 5

        # 清理目录条目中的点线（保留标题和页码）
        if is_toc:
            # 保留 "前言......1" 格式，但清理多余点号
            # 将 "...." 替换为制表符间隔
            import re
            cleaned = re.sub(r'\.{4,}', '\t', text)
            text = cleaned.strip()

        # 检测标题级别
        title_level = _detect_title_level(max_size, is_bold, text)
        is_title = title_level > 0

        # 检测首行缩进（正文中 x 明显大于左边距说明有缩进）
        first_line_indent = False
        if not is_title and not is_toc and max_size >= 11 and x > 100:
            first_line_indent = True

        # 检测对齐方式
        alignment = "left"
        if is_title:
            # 一级标题中的 "一、" "二、" 等左对齐
            if text.startswith(("一、", "二、", "三、", "四、", "五、",
                                "六、", "七、", "八、", "九、", "十、",
                                "十一、", "十二、")):
                alignment = "left"
            else:
                center_dist = abs(x + w / 2 - page_width / 2)
                if center_dist < 30:
                    alignment = "center"
                else:
                    alignment = "left"
        elif is_toc:
            alignment = "left"
        elif first_line_indent:
            alignment = "left"
        else:
            # 小字号检查居中（图表标题等）
            center_dist = abs(x + w / 2 - page_width / 2)
            if center_dist < 30 and max_size <= 11:
                alignment = "center"

        block = TextBlock(
            text=text,
            font_size=max_size,
            font_name=font_name,
            bold=is_bold,
            italic=is_italic,
            x=x, y=y, width=w, height=h,
            is_title=is_title,
            title_level=title_level,
            first_line_indent=first_line_indent,
            alignment=alignment,
            is_toc_entry=is_toc,
            spans_info=spans_info,
        )
        blocks.append(block)

    # === 合并逻辑 ===
    merged = []
    i = 0
    while i < len(blocks):
        current = blocks[i]

        # 1. 合并相邻的同级别短标题（如 "目"+"录" → "目录"）
        if current.is_title and len(current.text) <= 4:
            merged_text = current.text
            while i + 1 < len(blocks):
                next_block = blocks[i + 1]
                if (next_block.is_title
                        and next_block.title_level == current.title_level
                        and abs(next_block.font_size - current.font_size) < 2
                        and abs(next_block.y - current.y) < current.height * 3):
                    merged_text += next_block.text
                    i += 1
                else:
                    break
            current.text = merged_text
            merged.append(current)
            i += 1
            continue

        # 2. 合并短行 + 紧邻点线行（如 "前" + "言..........1"）
        # 当前行很短（<3字）且非标题，下一行是目录行且 y 间距很小
        if (not current.is_title and not current.is_toc_entry
                and len(current.text) <= 3
                and i + 1 < len(blocks)):
            next_block = blocks[i + 1]
            y_gap = abs(next_block.y - current.y)
            if (next_block.is_toc_entry
                    and y_gap < max(current.height * 2, 5)
                    and abs(next_block.font_size - current.font_size) < 2):
                # 合并：短文本前缀 + 目录行
                next_block.text = current.text + next_block.text
                i += 1
                merged.append(next_block)
                i += 1
                continue

        # 3. 正文行不合并，保持每行独立
        merged.append(current)
        i += 1

    return merged


def parse_pdf(pdf_path: str | Path) -> list[PageContent]:
    """解析 PDF 文件，返回每页的结构化内容"""
    doc = fitz.open(str(pdf_path))
    pages = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        content = PageContent(
            page_num=page_idx + 1,
            width=page.rect.width,
            height=page.rect.height,
        )

        page_width = page.rect.width

        # 提取表格（获取边界框用于过滤文本）
        table_blocks, table_bboxes = _extract_tables(page)
        content.table_blocks = table_blocks

        # 提取文本块（带格式信息）
        raw_blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

        lines_data = []
        for block in raw_blocks:
            if block["type"] == 0:  # 文本块
                for line in block.get("lines", []):
                    spans = []
                    for span in line.get("spans", []):
                        text = span.get("text", "")
                        if text.strip():
                            font_name = span.get("font", "")
                            is_bold = "bold" in font_name.lower() or "black" in font_name.lower()
                            is_italic = "italic" in font_name.lower() or "oblique" in font_name.lower()
                            spans.append((
                                text,
                                span.get("size", 12),
                                font_name,
                                is_bold,
                                is_italic,
                            ))

                    if spans:
                        lines_data.append({
                            "spans": spans,
                            "bbox": line["bbox"],
                        })

        # 合并为段落（传入表格边界避免重复提取）
        text_blocks = _merge_spans_to_blocks(lines_data, page_width, table_bboxes)
        content.text_blocks = text_blocks

        # 提取光栅图片
        images = page.get_images(full=True)
        for img_idx, img_info in enumerate(images):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                if base_image:
                    img_data = base_image["image"]
                    img_ext = base_image.get("ext", "png")
                    bbox = None
                    for item in page.get_image_info(xrefs=xref):
                        bbox = (item["bbox"][0], item["bbox"][1], item["bbox"][2], item["bbox"][3])
                        break

                    if bbox:
                        content.image_blocks.append(ImageBlock(
                            data=img_data,
                            x=bbox[0], y=bbox[1],
                            width=bbox[2] - bbox[0], height=bbox[3] - bbox[1],
                            ext=img_ext,
                        ))
            except Exception:
                continue

        # 过滤与已提取图片重叠的文本（图表标签等）
        for ib in content.image_blocks:
            img_bbox = (ib.x - 5, ib.y - 5, ib.x + ib.width + 5, ib.y + ib.height + 5)
            content.text_blocks = [
                tb for tb in content.text_blocks
                if not _text_in_chart_region(tb, img_bbox)
            ]

        # 检测并渲染矢量图表区域
        chart_regions = _detect_chart_regions(page, page_width, page.rect.height)
        for render_bbox, filter_bbox in chart_regions:
            try:
                img_data = _render_region_as_image(page, render_bbox, dpi=200)
                content.image_blocks.append(ImageBlock(
                    data=img_data,
                    x=render_bbox[0], y=render_bbox[1],
                    width=render_bbox[2] - render_bbox[0],
                    height=render_bbox[3] - render_bbox[1],
                    ext="png",
                    is_chart_render=True,
                ))
                # 过滤图表区域内的文本（保留图表外的标题/说明）
                content.text_blocks = [
                    tb for tb in content.text_blocks
                    if not _text_in_chart_region(tb, filter_bbox)
                ]
            except Exception:
                continue

        pages.append(content)

    doc.close()
    return pages


def image_bytes_to_numpy(data: bytes) -> np.ndarray:
    """将图片字节转为 numpy 数组"""
    img = Image.open(io.BytesIO(data))
    return np.array(img)
