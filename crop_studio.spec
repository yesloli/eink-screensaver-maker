# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置。

用法：
    pyinstaller --noconfirm --clean crop_studio.spec

产物在 dist/ 下，单文件、无控制台窗口。

运行时只需 Pillow + tkinterdnd2。tkinterdnd2 带 Tcl 包（tkdnd），
必须用 collect_all 把整个数据目录收进来，否则冻结后拖放会静默失效。
make_icon.py 与 _smoke.py 是开发期脚本，不进包。
"""

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = [], [], []
_d, _b, _h = collect_all("tkinterdnd2")
datas += _d
binaries += _b
hiddenimports += _h

# 运行时资源：图标（resource_path() 冻结后从 sys._MEIPASS 取）
datas += [("app.ico", ".")]

EXCLUDES = [
    "numpy", "onnxruntime", "networkx", "psutil", "flatbuffers",
    "tabulate", "protobuf", "fitz", "pymupdf", "pymupdf4llm",
    "matplotlib", "scipy", "pandas", "IPython", "pytest",
    "setuptools", "pip", "wheel",
]

a = Analysis(
    ["crop_studio.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="墨水屏阅读器屏保制作",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    icon="app.ico",
)
