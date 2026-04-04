<div align="center">

# PDF to Word Converter

### PDF 转 Word 智能转换工具

**一键将 PDF 文档转换为可编辑的 Word 文档，支持图表、表格、OCR 文字识别**

[![Version](https://img.shields.io/badge/version-1.0-blue.svg)](https://github.com/zhansongqiang/PDFTools)
[![Python](https://img.shields.io/badge/Python-3.10+-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-orange.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows-blue.svg)](https://github.com/zhansongqiang/PDFTools)

[功能特性](#-功能特性) · [快速开始](#-快速开始) · [使用说明](#-使用说明) · [技术架构](#-技术架构) · [更新日志](#-更新日志)

</div>

---

## 为什么选择 PDF to Word Converter？

> 在日常工作和学习中，我们经常需要编辑 PDF 文件中的内容。市面上的在线转换工具要么收费，要么存在隐私泄露风险，要么转换效果差强人意。
>
> **PDF to Word Converter** 是一款完全本地运行的免费开源工具，你的文件永远不会离开你的电脑。它不仅能准确提取文本和表格，还能智能识别图表区域，完美还原 PDF 排版效果。

## ✨ 功能特性

### 🎯 精准排版还原
- **多级标题识别** — 自动识别一级/二级/三级标题，保留字号和加粗格式
- **智能段落排版** — 检测首行缩进，正确合并段落，保持原始排版结构
- **目录完美保留** — 自动识别目录条目，保留点线引导符和页码

### 📊 图表智能处理
- **图片直接提取** — 精准提取 PDF 中的嵌入图片，居中显示
- **矢量图表渲染** — 自动检测矢量图表（柱状图、折线图等），渲染为高清图片嵌入 Word
- **标签去重过滤** — 智能过滤图表区域内的重复文本标签，避免排版混乱

### 📋 表格精准转换
- **结构化表格提取** — 准确提取表格数据，保留行列结构
- **格式完整保留** — 表格边框、居中对齐、表头加粗、垂直居中
- **自适应列宽** — 表格自动适应页面宽度

### 🔍 OCR 文字识别
- **图片文字提取** — 基于 PaddleOCR 引擎，识别 PDF 图片中的文字
- **中英文混合识别** — 同时支持中文和英文文字识别
- **可选启用** — 按需开启 OCR，不强制依赖

### 🌐 国际化支持
- **中英文界面切换** — 菜单栏一键切换界面语言，实时生效
- **完整翻译覆盖** — 所有界面元素、提示信息均已翻译

### 🖱️ 简洁易用的界面
- **拖拽上传** — 直接拖拽 PDF 文件到窗口即可添加
- **批量转换** — 支持同时添加多个文件批量处理
- **实时进度** — 后台线程转换，进度条实时反馈
- **自动打开** — 转换完成后自动打开输出目录

---

## 🚀 快速开始

### 环境要求
- Python 3.10 或更高版本
- Windows 操作系统（已测试 Windows 10/11）

### 安装依赖

```bash
# 克隆仓库
git clone https://github.com/zhansongqiang/PDFTools.git
cd PDFTools

# 安装基础依赖（文本/表格/图片转换）
pip install -r requirements.txt
```

### 运行程序

```bash
python main.py
```

### 免安装 EXE 版本

如果你不想安装 Python 环境，可以直接下载打包好的 EXE 版本：

1. 前往 [Releases 页面](https://github.com/zhansongqiang/PDFTools/releases) 下载最新版本
2. 解压后双击 `PDF转Word工具.exe` 即可运行
3. EXE 包含所有依赖（PyQt6、PaddleOCR、OpenCV 等），无需额外安装

> **注意**：EXE 版本体约 **500MB**（含 PaddleOCR、OpenCV 等 AI/CV 库），PaddleOCR 首次运行会自动下载模型文件（约 80MB）。

### 可选：启用 OCR 功能

如需提取图片中的文字，安装 OCR 引擎：

```bash
pip install paddleocr>=2.7,<3.0 paddlepaddle>=2.5,<3.0
```

> **注意**：PaddleOCR 首次运行会自动下载模型文件（约 80MB），请确保网络畅通。

---

## 📖 使用说明

1. **添加文件** — 拖拽 PDF 文件到窗口，或点击选择文件按钮
2. **选择输出目录** — 指定转换后 Word 文件的保存位置
3. **可选设置** — 勾选「启用 OCR 识别」以提取图片中的文字
4. **开始转换** — 点击「开始转换」按钮，等待进度条完成
5. **查看结果** — 转换完成后自动打开输出目录

---

## 🏗️ 技术架构

```
PDFTools/
├── main.py                  # 程序入口
├── requirements.txt         # 依赖清单
├── i18n/
│   ├── zh.json             # 中文翻译
│   └── en.json             # 英文翻译
├── core/
│   ├── pdf_parser.py       # PDF 解析引擎（PyMuPDF）
│   ├── ocr_engine.py       # OCR 识别引擎（PaddleOCR）
│   └── docx_builder.py     # Word 文档生成器
├── ui/
│   ├── main_window.py      # 主窗口（PyQt6）
│   ├── widgets.py          # 自定义控件（拖拽区域）
│   └── resources.py        # 样式资源
└── utils/
    └── i18n.py             # 国际化工具模块
```

### 核心技术栈

| 模块 | 技术 | 说明 |
|------|------|------|
| GUI 框架 | PyQt6 | 现代化桌面应用界面 |
| PDF 解析 | PyMuPDF (fitz) | 高性能 PDF 文本/图片/表格提取 |
| Word 生成 | python-docx | 标准 .docx 文档生成 |
| OCR 引擎 | PaddleOCR + PaddlePaddle | 百度开源 OCR，中英文识别 |
| 图片处理 | Pillow + NumPy | 图片格式转换与处理 |

---

## 📝 更新日志

### v1.0 (2026-04-03)

**首次发布，包含以下功能：**

- PDF 文本提取，保留标题层级和格式信息
- 智能目录识别与排版
- 表格结构化提取与格式保留
- 图片提取与矢量图表渲染
- 图表区域文本去重
- OCR 文字识别（PaddleOCR）
- 中英文界面切换
- 拖拽上传、批量转换、进度显示

---

## 🤝 参与贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 提交 Pull Request

---

## 📄 版权信息

- **作者**：zsq
- **版本**：1.0
- **联系邮箱**：11016795@qq.com
- **联系电话**：18820818283

---

<div align="center">

**如果这个工具对你有帮助，请给个 ⭐ Star 支持一下！**

[![Star History Chart](https://api.star-history.com/svg?repos=zhansongqiang/PDFTools&type=Date)](https://star-history.com/#zhansongqiang/PDFTools&Date)

</div>
