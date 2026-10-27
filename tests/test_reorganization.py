"""Structural regression tests for the organized v1.5 project."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
sys.path.insert(0, str(SRC))
import project_paths
import vlog_maker
import vlog_gui

class ReorganizationTest(unittest.TestCase):
    def test_project_paths(self):
        self.assertEqual(project_paths.ROOT, ROOT)
        self.assertEqual(vlog_maker.FFMPEG_DIR, ROOT/'tools')
        self.assertEqual(vlog_gui.ROOT, ROOT)

    def test_root_only_entry_files(self):
        self.assertEqual({p.name for p in ROOT.iterdir() if p.is_file()},
          {'man.txt','setup_windows.bat','start_gui.bat','start_release.bat','build_windows.bat'})

    def test_cli_entrypoint(self):
        child = subprocess.run([sys.executable,str(SRC/'app.py'),'--cli','--help'],
             capture_output=True,encoding='utf8',errors='replace',cwd=ROOT,timeout=15)
        self.assertEqual(child.returncode,0,child.stderr)
        self.assertIn('scan',child.stdout)

    def test_batch_links_exist(self):
        for name in ('start_gui.bat','start_release.bat','build_windows.bat','setup_windows.bat'):
            self.assertTrue((ROOT/name).is_file())
        self.assertTrue((ROOT/'scripts/windows/select_python.bat').is_file())
