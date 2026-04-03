"""样式和资源"""
STYLE_SHEET = """
QMainWindow {
    background-color: #f5f5f5;
}

QLabel {
    color: #333;
}

QPushButton#convertBtn {
    background-color: #4A90D9;
    color: white;
    border: none;
    padding: 10px 32px;
    border-radius: 5px;
    font-size: 14px;
    font-weight: bold;
}
QPushButton#convertBtn:hover {
    background-color: #357ABD;
}
QPushButton#convertBtn:pressed {
    background-color: #2A6099;
}
QPushButton#convertBtn:disabled {
    background-color: #ccc;
    color: #999;
}

QGroupBox {
    font-weight: bold;
    border: 1px solid #ddd;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

QProgressBar {
    border: 1px solid #ddd;
    border-radius: 4px;
    text-align: center;
    height: 22px;
    background: white;
}
QProgressBar::chunk {
    background-color: #4A90D9;
    border-radius: 3px;
}

QLineEdit {
    padding: 6px 10px;
    border: 1px solid #ddd;
    border-radius: 4px;
    background: white;
    font-size: 13px;
}

QCheckBox {
    spacing: 6px;
    font-size: 13px;
}

QComboBox {
    padding: 4px 8px;
    border: 1px solid #ddd;
    border-radius: 4px;
    background: white;
}

QMenuBar {
    background-color: #f0f0f0;
    border-bottom: 1px solid #ddd;
}
QMenuBar::item:selected {
    background-color: #4A90D9;
    color: white;
}
QMenu {
    background-color: white;
    border: 1px solid #ddd;
}
QMenu::item:selected {
    background-color: #4A90D9;
    color: white;
}
"""
