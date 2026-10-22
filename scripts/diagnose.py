"""Offline, non-mutating Windows setup diagnostics for AI Vlog Maker."""
import importlib.util
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def status(label, ok, details=''):
    print(f"[{'OK' if ok else 'MISSING'}] {label}" + (f': {details}' if details else ''))
    return bool(ok)

def executable(name):
    local = ROOT / 'tools' / (name + '.exe' if os.name == 'nt' else name)
    return str(local) if local.is_file() else shutil.which(name)

def main():
    print('AI Vlog Maker - environment check (no files modified)')
    print('Python:', sys.version.split()[0], sys.executable)
    print('Platform:', platform.platform())
    ready = True
    for label, module in [('PySide6', 'PySide6'), ('python-vlc', 'vlc'), ('PyInstaller', 'PyInstaller')]:
        ok = importlib.util.find_spec(module) is not None
        ready = status(label, ok) and ready
    for name in ('ffmpeg','ffprobe'):
        cmd = executable(name)
        ready = status(name, bool(cmd), cmd or 'not found') and ready
    status('Ollama command', bool(shutil.which('ollama')), shutil.which('ollama') or 'not found in PATH')
    vlc_paths = []
    for v in (os.getenv('VLC_DIR'), os.getenv('ProgramFiles'), os.getenv('ProgramFiles(x86)')):
        if v:
            p = Path(v)
            candidates = [p / 'libvlc.dll', p / 'VideoLAN' / 'VLC' / 'libvlc.dll']
            vlc_paths.extend(str(x) for x in candidates if x.is_file())
    status('VLC libvlc.dll', bool(vlc_paths), vlc_paths[0] if vlc_paths else 'install 64-bit VLC for video preview')
    print('APP entry:', 'app.py found' if (ROOT/'app.py').is_file() else 'app.py missing')
    print('Note: External AI models and Windows GUI/EXE behavior require separate manual testing.')
    return 0 if ready else 1

if __name__ == '__main__':
    raise SystemExit(main())
