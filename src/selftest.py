"""Headless packaged-app smoke test used by the Windows installation wizard.

Does not claim to test real-time Qt playback or a complete rendered movie.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import urlopen, Request
import tempfile


def run(report_path: str) -> int:
    checks = []

    def check(name, callback):
        try:
            result = callback()
            checks.append({"name": name, "ok": True, "detail": str(result)[:240]})
        except Exception as exc:
            checks.append({"name": name, "ok": False, "detail": str(exc)[:240]})

    def qt():
        from PySide6.QtCore import qVersion
        from PySide6.QtWidgets import QApplication
        return f"Qt {qVersion()}, QApplication available"

    def binary(name):
        from project_paths import TOOLS
        exe = TOOLS / (name + '.exe' if os.name == 'nt' else name)
        if not exe.is_file():
            raise FileNotFoundError(exe)
        p = subprocess.run([str(exe), '-version'], capture_output=True,
                           timeout=12, check=True)
        return p.stdout.decode('utf-8', 'replace').splitlines()[0]

    def vlc():
        from vlc_loader import import_vlc
        package = import_vlc()
        v = package.libvlc_get_version()
        return v.decode('utf-8', 'replace') if isinstance(v, bytes) else str(v)

    def ollama():
        address = os.environ.get('AI_VLOG_OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')
        with urlopen(address + '/api/tags', timeout=6) as response:
            document = json.load(response)
        available = {r.get('name') for r in document.get('models', [])}
        required = {x.strip() for x in os.environ.get('AI_VLOG_REQUIRED_MODELS', '').split(',') if x.strip()}
        missing = sorted(required - available)
        if missing:
            raise RuntimeError('Required models missing: ' + ', '.join(missing))
        return f"{address}: {len(available)} model(s); selected models present"

    def render_sample():
        from project_paths import TOOLS
        ffmpeg = TOOLS / ('ffmpeg.exe' if os.name == 'nt' else 'ffmpeg')
        ffprobe = TOOLS / ('ffprobe.exe' if os.name == 'nt' else 'ffprobe')
        with tempfile.TemporaryDirectory() as folder:
            movie = str(Path(folder) / 'render-smoke.mp4')
            subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-y',
                            '-f', 'lavfi', '-i', 'color=c=black:s=160x90:r=10',
                            '-t', '0.6', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', movie],
                           check=True, capture_output=True, timeout=30)
            if not Path(movie).is_file() or Path(movie).stat().st_size < 100:
                raise RuntimeError('FFmpeg did not produce MP4')
            probe = subprocess.run([str(ffprobe), '-v', 'error', '-show_entries',
                                    'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1',
                                    movie], check=True, capture_output=True, timeout=15)
            seconds = float(probe.stdout.decode('utf-8').strip())
            if not 0.3 <= seconds <= 1.5:
                raise RuntimeError(f'Invalid MP4 duration: {seconds}')
            return f'Video export OK ({seconds:.2f}s)'

    def inference():
        address = os.environ.get('AI_VLOG_OLLAMA_URL', 'http://127.0.0.1:11434').rstrip('/')
        choices = [s.strip() for s in os.environ.get('AI_VLOG_REQUIRED_MODELS','').split(',') if s.strip()]
        if not choices:
            raise ValueError('No models selected')
        model = 'gemma3:4b' if 'gemma3:4b' in choices else choices[0]
        body = json.dumps({'model': model, 'prompt': 'Reply with one word: OK.',
                           'stream': False, 'options': {'num_predict': 5}}).encode('utf-8')
        req = Request(address + '/api/generate', data=body,
                      headers={'Content-Type': 'application/json'}, method='POST')
        with urlopen(req, timeout=180) as response:
            document = json.load(response)
        if 'response' not in document:
            raise RuntimeError('Ollama did not return generated text')
        return f'{model}: inference completed'

    check('PySide6', qt)
    check('FFmpeg', lambda: binary('ffmpeg'))
    check('FFprobe', lambda: binary('ffprobe'))
    check('LibVLC', vlc)
    check('Ollama + selected models', ollama)
    check('MP4 encode/decode', render_sample)
    check('Ollama inference', inference)
    result = {'ok': all(x['ok'] for x in checks), 'checks': checks}
    file = Path(report_path)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['ok'] else 1
