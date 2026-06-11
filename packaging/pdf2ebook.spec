# PyInstaller spec: standalone pdf2ebook.exe
# Double-clicking the exe (no arguments) launches the local web UI.
# Build:  pyinstaller packaging/pdf2ebook.spec

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    ("../src/pdf2ebook/fonts", "pdf2ebook/fonts"),
    ("../src/pdf2ebook/webui/static", "pdf2ebook/webui/static"),
]
datas += collect_data_files("pypdfium2_raw")

hiddenimports = (
    collect_submodules("uvicorn")
    + ["pdf2ebook.ocrmode", "pdf2ebook.webui.app", "pdf2ebook.send"]
)

a = Analysis(
    ["entry.py"],
    pathex=["../src"],
    datas=datas,
    hiddenimports=hiddenimports,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="pdf2ebook",
    console=True,
    upx=False,
)
