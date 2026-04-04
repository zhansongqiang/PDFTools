"""PDF 解析模块 - 使用 PyMuPDF 提取文本、图片、表格
Copyright (c) 2026 zsq. All rights reserved.
版本: 1.0
联系邮箱: 11016795@qq.com
联系电话: 18820818283

参考 pdf2docx 等开源项目的架构，实现：
- 文档级统计（基准字号、平均行距）
- 智能段落重建（跨行合并）
- 相对字号标题检测
- 页眉页脚过滤
"""
from __future__ import annotations

import io
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image
import numpy as np


# ==================== 数据结构 ====================

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
    is_title: bool = False
    title_level: int = 0  # 1=一级, 2=二级, 3=三级, 0=正文
    first_line_indent: bool = False
    alignment: str = "left"
    is_page_num: bool = False
    is_toc_entry: bool = False
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
    is_chart_render: bool = False


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


@dataclass
class DocumentStats:
    """文档级统计数据"""
    body_font_size: float = 12.0       # 正文字号（出现频率最高的）
    avg_line_height: float = 14.0      # 平均行高
    avg_line_spacing: float = 16.0     # 平均行距（y 坐标差）
    left_margin: float = 90.0          # 左边距基准


# ==================== 辅助函数 ====================

def _detect_chart_regions(page, page_width: float, page_height: float) -> list[tuple]:
    """检测页面中的矢量图表区域"""
    try:
        drawings = page.get_drawings()
    except Exception:
        return []

    if len(drawings) < 5:
        return []

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

    union = rects[0]
    for r in rects[1:]:
        union |= r

    chart_area = union.width * union.height
    page_area = page_width * page_height
    area_ratio = chart_area / page_area

    is_chart = (area_ratio > 0.10 and has_color_fill) or area_ratio > 0.25
    if not is_chart:
        return []

    margin_side = 30
    render_bbox = (
        max(0, union.x0 - margin_side),
        max(0, union.y0 - margin_side),
        min(page_width, union.x1 + margin_side),
        min(page_height, union.y1 + 15),
    )
    filter_bbox = (union.x0 - 5, union.y0 - 5, union.x1 + 5, union.y1 + 5)

    return [(render_bbox, filter_bbox)]


def _render_region_as_image(page, bbox: tuple, dpi: int = 200) -> bytes:
    """将页面区域渲染为 PNG"""
    clip = fitz.Rect(bbox)
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, clip=clip)
    return pix.tobytes("png")


def _text_in_chart_region(block: TextBlock, filter_bbox: tuple) -> bool:
    """检查文本块是否在区域内"""
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
    if text.isdigit() and abs(x + len(text) * 5 - page_width / 2) < 50:
        return True
    if text.isdigit() and font_size <= 10:
        return True
    return False


def _extract_tables(page) -> tuple[list[TableBlock], list]:
    """提取表格"""
    table_blocks = []
    table_bboxes = []

    try:
        table_finder = page.find_tables()
        if hasattr(table_finder, 'tables'):
            tables = table_finder.tables
        else:
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


# ==================== 文档级统计 ====================

def _analyze_document_stats(all_pages_lines: list) -> DocumentStats:
    """分析文档级统计信息（参考 pdf2docx 的全局分析方法）

    扫描全部页面，统计：
    1. 出现频率最高的字号 = 正文基准字号
    2. 平均行高和行距
    3. 左边距基准
    """
    font_size_counter = Counter()
    line_heights = []
    line_spacings = []
    x_positions = []

    for page_lines in all_pages_lines:
        prev_y = None
        for line_info in page_lines:
            spans = line_info["spans"]
            bbox = line_info["bbox"]
            if not spans:
                continue

            # 收集字号（排除 TOC/表格等小字，只统计 >= 11pt）
            sizes = [s[1] for s in spans if s[1] >= 11]
            if sizes:
                line_sizes = Counter(sizes)
                dominant_size = line_sizes.most_common(1)[0][0]
                font_size_counter[round(dominant_size, 1)] += 1

            # 行高
            h = bbox[3] - bbox[1]
            if h > 0:
                line_heights.append(h)

            # 行距
            y = bbox[1]
            if prev_y is not None and y > prev_y:
                spacing = y - prev_y
                if spacing < 100:  # 排除大间距（跨段落/跨标题）
                    line_spacings.append(spacing)
            prev_y = y

            # x 位置（用于判断左边距）
            x_positions.append(bbox[0])

    # 基准字号
    body_font_size = 12.0
    if font_size_counter:
        body_font_size = font_size_counter.most_common(1)[0][0]

    # 平均行高
    avg_line_height = 14.0
    if line_heights:
        avg_line_height = sum(line_heights) / len(line_heights)

    # 平均行距
    avg_line_spacing = avg_line_height * 1.2
    if line_spacings:
        avg_line_spacing = sum(line_spacings) / len(line_spacings)

    # 左边距（取最常见的 x 位置）
    left_margin = 90.0
    if x_positions:
        # 四舍五入到整数，找最常见的
        rounded_x = [round(x) for x in x_positions]
        x_counter = Counter(rounded_x)
        left_margin = x_counter.most_common(1)[0][0]

    return DocumentStats(
        body_font_size=body_font_size,
        avg_line_height=avg_line_height,
        avg_line_spacing=avg_line_spacing,
        left_margin=left_margin,
    )


# ==================== 标题检测 ====================

# 中文标题格式模式
_HEADING_PATTERNS = [
    re.compile(r'^第[一二三四五六七八九十百]+[章节部分]'),  # 第一章、第二节
    re.compile(r'^[一二三四五六七八九十]+[、．]'),          # 一、 二．
    re.compile(r'^[（(][一二三四五六七八九十]+[）)]'),      # （一）(二)
    re.compile(r'^\d+[、．.]\s*\S'),                       # 1. xxx、2．xxx
    re.compile(r'^附[录件]'),                              # 附录、附件
]


def _detect_title_level(font_size: float, bold: bool, text: str,
                        stats: DocumentStats) -> int:
    """智能标题检测（参考 pdf2docx 相对字号 + 文本模式）

    改进：
    1. 使用相对字号（基于文档正文基准字号）
    2. 结合文本模式（一、（一）、1. 等）
    3. 考虑加粗状态
    """
    body_size = stats.body_font_size

    # 文本模式匹配（中文标题格式）
    has_heading_pattern = any(p.match(text.strip()) for p in _HEADING_PATTERNS)

    # 相对字号比例
    ratio = font_size / body_size if body_size > 0 else 1.0

    # 大标题/封面
    if ratio >= 1.8 or font_size >= 20:
        return 1

    # 一级标题
    if ratio >= 1.4 or font_size >= 17:
        if has_heading_pattern or bold or ratio >= 1.6:
            return 1
        return 2  # 大字号但无标题特征，降为二级

    # 二级标题
    if ratio >= 1.3 or font_size >= 14.5:
        if has_heading_pattern or bold:
            return 2
        # 大字号但无标题特征，可能是正文中较大的注释文字
        if ratio >= 1.5:
            return 3
        return 0

    # 三级标题：需要明确的标题模式 + 加粗，或字号显著大于正文
    if has_heading_pattern and (bold or ratio >= 1.2):
        return 3

    # 正文
    return 0


# ==================== 页眉页脚检测 ====================

def _detect_headers_footers(all_pages_lines: list, page_heights: list[float]) -> set:
    """检测页眉页脚区域（参考常见文档分析算法）

    策略：对比连续3页，相同位置出现相同文本即为页眉/页脚
    返回需要排除的行索引集合（page_idx, line_idx）
    """
    if len(all_pages_lines) < 3:
        return set()

    exclude = set()

    # 收集每页顶部和底部区域的文本
    page_regions = []
    for page_idx, page_lines in enumerate(all_pages_lines):
        page_height = page_heights[page_idx] if page_idx < len(page_heights) else 800
        top_threshold = page_height * 0.08
        bottom_threshold = page_height * 0.90

        top_texts = []
        bottom_texts = []
        for line_idx, line_info in enumerate(page_lines):
            bbox = line_info["bbox"]
            text = "".join(s[0] for s in line_info["spans"]).strip()
            if not text:
                continue

            y = bbox[1]
            if y < top_threshold:
                top_texts.append((line_idx, text[:30], round(y)))
            elif y > bottom_threshold:
                bottom_texts.append((line_idx, text[:30], round(y)))

        page_regions.append({"top": top_texts, "bottom": bottom_texts})

    # 检测页眉：连续3页顶部相同位置出现相同文本
    for i in range(len(page_regions) - 2):
        for t1 in page_regions[i]["top"]:
            for t2 in page_regions[i + 1]["top"]:
                if t1[1] == t2[1] and abs(t1[2] - t2[2]) < 10:
                    for t3 in page_regions[i + 2]["top"]:
                        if t1[1] == t3[1] and abs(t1[2] - t3[2]) < 10:
                            exclude.add((i, t1[0]))
                            exclude.add((i + 1, t2[0]))
                            exclude.add((i + 2, t3[0]))

    # 检测页脚
    for i in range(len(page_regions) - 2):
        for b1 in page_regions[i]["bottom"]:
            for b2 in page_regions[i + 1]["bottom"]:
                if b1[1] == b2[1] and abs(b1[2] - b2[2]) < 10:
                    for b3 in page_regions[i + 2]["bottom"]:
                        if b1[1] == b3[1] and abs(b1[2] - b3[2]) < 10:
                            exclude.add((i, b1[0]))
                            exclude.add((i + 1, b2[0]))
                            exclude.add((i + 2, b3[0]))

    return exclude


# ==================== 段落重建 ====================

def _line_to_block(line_info: dict, page_width: float, table_bboxes: list,
                   stats: DocumentStats) -> TextBlock | None:
    """将单行数据转为 TextBlock"""
    spans = line_info["spans"]
    bbox = line_info["bbox"]

    if not spans:
        return None

    if _is_in_table(bbox, table_bboxes):
        return None

    # 合并同一行所有 span
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
        return None

    # 过滤页码
    if _is_page_number(text, bbox[0], page_width, max_size):
        return None

    # 过滤纯点线
    clean = text.replace(".", "").replace(" ", "").replace("\u3000", "")
    if clean == "" and "." in text:
        return None

    x = bbox[0]
    y = bbox[1]
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]

    # 检测目录条目
    is_toc = "..." in text and text.count(".") > 5
    if is_toc:
        cleaned = re.sub(r'\.{4,}', '\t', text)
        text = cleaned.strip()

    # 检测标题级别（TOC 条目不参与标题检测）
    if is_toc:
        title_level = 0
        is_title = False
    else:
        title_level = _detect_title_level(max_size, is_bold, text, stats)
        is_title = title_level > 0

    # 检测首行缩进（相对于文档左边距偏移 > 5pt）
    first_line_indent = False
    indent_threshold = stats.left_margin + 5
    if not is_title and not is_toc and max_size >= stats.body_font_size * 0.9:
        if x > indent_threshold:
            first_line_indent = True

    # 对齐检测
    alignment = "left"
    if is_title:
        if text.startswith(("一、", "二、", "三、", "四、", "五、",
                            "六、", "七、", "八、", "九、", "十、",
                            "十一、", "十二、")):
            alignment = "left"
        else:
            center_dist = abs(x + w / 2 - page_width / 2)
            alignment = "center" if center_dist < 30 else "left"
    elif is_toc:
        alignment = "left"
    elif first_line_indent:
        alignment = "left"
    else:
        # 正文居中检测：只有小字号（< 基准字号）且宽度很窄的才判为居中
        # 如 "图1 xxx"、"表1 xxx" 等图表标题
        center_dist = abs(x + w / 2 - page_width / 2)
        if (center_dist < 30
                and max_size < stats.body_font_size
                and w < page_width * 0.6):
            alignment = "center"

    return TextBlock(
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


def _reconstruct_paragraphs(blocks: list[TextBlock], stats: DocumentStats) -> list[TextBlock]:
    """段落重建算法（参考 pdf2docx 两阶段算法）

    阶段1：合并相邻短标题（"目"+"录" → "目录"）
    阶段2：合并连续正文行为完整段落
    """
    if not blocks:
        return blocks

    # === 阶段1：短标题合并 ===
    merged = []
    i = 0
    while i < len(blocks):
        current = blocks[i]

        # 合并相邻的同级别短标题
        if current.is_title and len(current.text) <= 4:
            merged_text = current.text
            total_width = current.width
            total_spans = list(current.spans_info)
            while i + 1 < len(blocks):
                next_block = blocks[i + 1]
                if (next_block.is_title
                        and next_block.title_level == current.title_level
                        and abs(next_block.font_size - current.font_size) < 2
                        and abs(next_block.y - current.y) < current.height * 3):
                    merged_text += next_block.text
                    total_width += next_block.width
                    total_spans.extend(next_block.spans_info)
                    i += 1
                else:
                    break
            current.text = merged_text
            current.width = total_width
            current.spans_info = total_spans
            merged.append(current)
            i += 1
            continue

        # 合并短行 + 紧邻目录行（"前" + "言..........1"）
        if (not current.is_title and not current.is_toc_entry
                and len(current.text) <= 3
                and i + 1 < len(blocks)):
            next_block = blocks[i + 1]
            y_gap = abs(next_block.y - current.y)
            if (next_block.is_toc_entry
                    and y_gap < max(current.height * 2, 5)
                    and abs(next_block.font_size - current.font_size) < 2):
                next_block.text = current.text + next_block.text
                next_block.spans_info = current.spans_info + next_block.spans_info
                i += 1
                merged.append(next_block)
                i += 1
                continue

        merged.append(current)
        i += 1

    # === 阶段2：正文段落重建 ===
    result = []
    i = 0
    while i < len(merged):
        block = merged[i]

        # 标题、TOC、特殊元素不参与正文合并
        if block.is_title or block.is_toc_entry or block.alignment == "center":
            result.append(block)
            i += 1
            continue

        # 首行缩进 → 新段落起点，尝试合并后续正文行
        if block.first_line_indent:
            paragraph_text = block.text
            paragraph_spans = list(block.spans_info)
            last_y = block.y
            last_h = block.height
            last_x = block.x
            j = i + 1

            while j < len(merged):
                next_b = merged[j]
                # 停止条件
                if next_b.is_title or next_b.is_toc_entry:
                    break
                if next_b.alignment == "center":
                    break
                if next_b.first_line_indent:
                    break  # 下一段落开始

                # 行间距检查
                y_gap = next_b.y - (last_y + last_h)
                max_gap = stats.avg_line_spacing * 1.5
                if y_gap > max(max_gap, 5):
                    break

                # 字号检查（同一段落内字号应一致）
                if abs(next_b.font_size - block.font_size) > 1.5:
                    break

                # x 位置检查：后续行应在正文的 x 位置（非首行缩进）
                # 首行 x 较大（缩进），后续行 x 应接近左边距
                # 如果后续行的 x 接近首行缩进位置，可能是新段落
                if next_b.x > block.x + 5 and next_b.x > stats.left_margin + 15:
                    break

                # 合并
                paragraph_text += next_b.text
                paragraph_spans.extend(next_b.spans_info)
                last_y = next_b.y
                last_h = next_b.height
                last_x = next_b.x
                j += 1

            block.text = paragraph_text
            block.spans_info = paragraph_spans
            result.append(block)
            i = j
            continue

        # 非首行缩进的正文行
        # 检查是否和上一个结果段落可以合并（上一段落未闭合）
        if result and not result[-1].is_title and not result[-1].is_toc_entry:
            prev = result[-1]
            y_gap = block.y - (prev.y + prev.height)
            max_gap = stats.avg_line_spacing * 1.5
            # 如果间距紧凑且字号一致，合并到上一个段落
            if (y_gap <= max(max_gap, 3)
                    and abs(block.font_size - prev.font_size) < 1.5
                    and not block.first_line_indent
                    and prev.alignment != "center"):
                prev.text += block.text
                prev.spans_info.extend(block.spans_info)
                prev.y = block.y  # 更新 y 到最后一行
                prev.height = block.height
                i += 1
                continue

        result.append(block)
        i += 1

    return result


# ==================== 主解析函数 ====================

def parse_pdf(pdf_path: str | Path) -> list[PageContent]:
    """解析 PDF 文件，返回每页的结构化内容

    改进流程：
    1. 第一遍扫描：收集全部页面原始数据 + 文档级统计
    2. 检测页眉页脚
    3. 第二遍处理：标题检测 + 段落重建
    """
    doc = fitz.open(str(pdf_path))

    # === 第一遍：收集原始数据 ===
    all_pages_raw_lines = []
    all_pages_page_widths = []
    all_pages_page_heights = []
    all_pages_tables = []
    all_pages_table_bboxes = []
    all_pages_images = []
    all_pages_chart_regions = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_width = page.rect.width
        page_height = page.rect.height

        all_pages_page_widths.append(page_width)
        all_pages_page_heights.append(page_height)

        # 提取表格
        table_blocks, table_bboxes = _extract_tables(page)
        all_pages_tables.append(table_blocks)
        all_pages_table_bboxes.append(table_bboxes)

        # 提取原始文本行
        raw_blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        lines_data = []
        for block in raw_blocks:
            if block["type"] == 0:
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

        all_pages_raw_lines.append(lines_data)

        # 提取光栅图片
        images = []
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            try:
                base_image = doc.extract_image(xref)
                if base_image:
                    img_data = base_image["image"]
                    img_ext = base_image.get("ext", "png")
                    bbox = None
                    for item in page.get_image_info(xrefs=xref):
                        bbox = (item["bbox"][0], item["bbox"][1],
                                item["bbox"][2], item["bbox"][3])
                        break
                    if bbox:
                        images.append(ImageBlock(
                            data=img_data,
                            x=bbox[0], y=bbox[1],
                            width=bbox[2] - bbox[0], height=bbox[3] - bbox[1],
                            ext=img_ext,
                        ))
            except Exception:
                continue
        all_pages_images.append(images)

        # 检测矢量图表区域
        chart_regions = _detect_chart_regions(page, page_width, page_height)
        all_pages_chart_regions.append(chart_regions)

    # === 文档级统计 ===
    stats = _analyze_document_stats(all_pages_raw_lines)

    # === 页眉页脚检测 ===
    header_footer_lines = _detect_headers_footers(
        all_pages_raw_lines, all_pages_page_heights
    )

    # === 第二遍：构建结构化内容 ===
    pages = []
    prev_page_last_block = None  # 用于跨页段落合并

    for page_idx in range(len(doc)):
        page_width = all_pages_page_widths[page_idx]
        table_bboxes = all_pages_table_bboxes[page_idx]

        content = PageContent(
            page_num=page_idx + 1,
            width=page_width,
            height=all_pages_page_heights[page_idx],
        )

        # 表格
        content.table_blocks = all_pages_tables[page_idx]

        # 文本块（排除页眉页脚）
        lines_data = all_pages_raw_lines[page_idx]
        filtered_lines = []
        for line_idx, line_info in enumerate(lines_data):
            if (page_idx, line_idx) in header_footer_lines:
                continue
            filtered_lines.append(line_info)

        # 转为 TextBlock
        blocks = []
        for line_info in filtered_lines:
            block = _line_to_block(line_info, page_width, table_bboxes, stats)
            if block is not None:
                blocks.append(block)

        # 段落重建
        blocks = _reconstruct_paragraphs(blocks, stats)

        # 跨页段落合并
        if prev_page_last_block and blocks:
            first = blocks[0]
            if (not prev_page_last_block.is_title
                    and not prev_page_last_block.is_toc_entry
                    and not first.is_title
                    and not first.is_toc_entry
                    and not first.first_line_indent
                    and abs(first.font_size - prev_page_last_block.font_size) < 1.5):
                prev_page_last_block.text += first.text
                prev_page_last_block.spans_info.extend(first.spans_info)
                blocks.pop(0)

        content.text_blocks = blocks

        # 图片
        content.image_blocks = all_pages_images[page_idx]

        # 过滤图片区域重叠文本
        for ib in content.image_blocks:
            img_bbox = (ib.x - 5, ib.y - 5, ib.x + ib.width + 5, ib.y + ib.height + 5)
            content.text_blocks = [
                tb for tb in content.text_blocks
                if not _text_in_chart_region(tb, img_bbox)
            ]

        # 矢量图表
        for render_bbox, filter_bbox in all_pages_chart_regions[page_idx]:
            try:
                page = doc[page_idx]
                img_data = _render_region_as_image(page, render_bbox, dpi=200)
                content.image_blocks.append(ImageBlock(
                    data=img_data,
                    x=render_bbox[0], y=render_bbox[1],
                    width=render_bbox[2] - render_bbox[0],
                    height=render_bbox[3] - render_bbox[1],
                    ext="png",
                    is_chart_render=True,
                ))
                content.text_blocks = [
                    tb for tb in content.text_blocks
                    if not _text_in_chart_region(tb, filter_bbox)
                ]
            except Exception:
                continue

        # 记录本页最后一个文本块（用于跨页合并）
        if content.text_blocks:
            prev_page_last_block = content.text_blocks[-1]
        else:
            prev_page_last_block = None

        pages.append(content)

    doc.close()
    return pages


def image_bytes_to_numpy(data: bytes) -> np.ndarray:
    """将图片字节转为 numpy 数组"""
    img = Image.open(io.BytesIO(data))
    return np.array(img)
