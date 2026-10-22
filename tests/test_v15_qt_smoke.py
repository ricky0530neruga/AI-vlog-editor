"""Optional Qt smoke test; requires PySide6 and a display (or QT_QPA_PLATFORM=offscreen)."""
import importlib.util
import os
import tempfile
import unittest


@unittest.skipUnless(importlib.util.find_spec('PySide6'),'PySide6 not installed in test environment')
class QtSmoke(unittest.TestCase):
    def test_main_window_and_pages(self):
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        from vlog_qt import EditorWindow
        app=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            from unittest.mock import patch
            from pathlib import Path
            with patch('qt_store.CONFIG',Path(tmp)/'settings.json'):
                w=EditorWindow()
                self.assertEqual(w.pages.count(),3)
                self.assertEqual(w.nav.count(),3)
                self.assertEqual(w.plan.columnCount(),4)
                self.assertEqual(w.candidates.columnCount(),5)
                w.close()
        self.assertIsNotNone(app)

if __name__=='__main__':unittest.main()
