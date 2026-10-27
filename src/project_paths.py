"""Project paths for source runs and PyInstaller onedir releases."""
from pathlib import Path
import sys

def project_root():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent

ROOT = project_root()
SOURCE = ROOT / 'src' if not getattr(sys, 'frozen', False) else ROOT
TOOLS = ROOT / 'tools'
