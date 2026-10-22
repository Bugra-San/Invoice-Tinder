# PyInstaller-Bauanleitung für RechnungsTinder.exe (ein einziges Programm, ohne Python-Installation)
#
#   pip install -r requirements.txt pyinstaller pillow
#   pyinstaller packaging/RechnungsTinder.spec
#
# Ergebnis: dist/RechnungsTinder.exe (bzw. dist/RechnungsTinder unter Linux/macOS)
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "packaging" / "rechnungs_tinder_start.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "rechnungs_tinder" / "static"), "rechnungs_tinder/static")],
    hiddenimports=["rechnungs_tinder.__main__", *collect_submodules("waitress")],
    excludes=["pytest", "numpy", "PIL", "playwright"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name="RechnungsTinder",
    console=True,  # Fenster zeigt Adresse und PIN
    icon=str(ROOT / "rechnungs_tinder" / "static" / "icon-512.png"),
)
