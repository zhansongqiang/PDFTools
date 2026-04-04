# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('i18n', 'i18n')],
    hiddenimports=['docx', 'fitz', 'paddleocr', 'paddle'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 未使用的深度学习框架
        'tensorflow', 'keras', 'tensorboard', 'torch', 'torchvision', 'torchaudio',
        # 未使用的科学计算/数据处理
        'scipy', 'pandas', 'pyarrow', 'skimage', 'sympy',
        # 未使用的多媒体/图像处理
        'matplotlib', 'moviepy', 'imageio', 'imageio_ffmpeg', 'librosa', 'soundfile',
        # 未使用的旧版/替代库
        'PyQt5', 'tkinter', 'PIL.ImageQt',
        # 未使用的开发/笔记工具
        'onnx', 'onnxruntime', 'IPython', 'notebook', 'jupyter', 'pytest',
        # 未使用的其他
        'sqlalchemy', 'gradio', 'streamlit', 'fastapi', 'flask', 'django',
        'win32com', 'pythoncom', 'pywintypes',
        'tornado', 'zmq',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PDF转Word工具',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='NONE',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='PDF转Word工具',
)
