"""Run all source-level tests without needing to put Python files in project root."""
import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'src'))
suite = unittest.defaultTestLoader.discover(str(PROJECT / 'tests'), pattern='test_*.py', top_level_dir=str(PROJECT / 'tests'))
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
