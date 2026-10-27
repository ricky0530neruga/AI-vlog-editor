"""Installer compatibility tests runnable without Windows or external binaries."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import json
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

class InstallerContractTests(unittest.TestCase):
    def test_installer_has_five_pages(self):
        source=(ROOT/'installer'/'setup_wizard.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('for($i=0;$i -lt 5;$i++)',source)
        for heading in ('檢查目前環境','安裝項目清單','選擇安裝位置','選擇 Ollama 模型','安裝與最終功能檢查'):
            self.assertIn(heading,source)

    def test_private_ollama_port_is_supported_in_ai_and_gui(self):
        for name in ('vlog_maker.py','vlog_qt.py'):
            self.assertIn('AI_VLOG_OLLAMA_URL',(ROOT/'src'/name).read_text(encoding='utf-8'))

    def test_portable_config_and_workspace_under_root(self):
        with patch.dict(os.environ,{'AI_VLOG_PORTABLE':'1'}):
            sys.modules.pop('qt_store', None)
            import qt_store
            self.assertEqual(qt_store.DEFAULT_OUT, str(qt_store._DATA_ROOT/'Workspaces'))
            self.assertEqual(qt_store.CONFIG, qt_store._DATA_ROOT/'Data'/'gui_settings.json')
        sys.modules.pop('qt_store', None)

    def test_selftest_report_writes_failure_without_dependencies(self):
        import selftest
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'AI_VLOG_OLLAMA_URL':'http://127.0.0.1:1','AI_VLOG_REQUIRED_MODELS':'gemma3:4b'}):
            dest=Path(folder)/'log'/'selftest.json'
            result=selftest.run(str(dest))
            self.assertEqual(result,1)
            data=json.loads(dest.read_text(encoding='utf-8'))
            self.assertFalse(data['ok'])
            self.assertEqual(len(data['checks']),7)

    def test_includes_official_sha256_pins(self):
        core=(ROOT/'installer'/'installer_core.ps1').read_text(encoding='utf-8-sig')
        self.assertIn('e6527768c53e85ec4596495fb0f035ef07f437b4b591ebc3581684699a4668f4',core)
        self.assertIn('fcf30850371ad10c9373cc4f0f4501e7dee49e3e9ae9f20c72fb2661a1ca6323',core)

if __name__ == '__main__': unittest.main()
