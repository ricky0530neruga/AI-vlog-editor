import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import benchmark_v16 as bench
import vlog_maker as core


class BenchmarkTests(unittest.TestCase):
    def test_manifest_stable_and_detects_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'a.mp4';source.write_bytes(b'fixed')
            a=bench.manifest([source]);self.assertEqual(a,bench.manifest([source]))
            self.assertEqual(bench.annotation_template(a)['status'],'尚未評估')
            source.write_bytes(b'other')
            with self.assertRaises(ValueError):bench.verify_manifest(a)

    def test_replay_deterministic_and_readonly(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);db=core.connect(root/'work')
            db.execute('INSERT INTO media(path,kind,duration,mtime) VALUES(?,?,?,?)',('demo.mp4','video',20,1))
            core.candidates(db,8,36)
            db.execute("UPDATE candidates SET score=80,event=50,v2=1,category='city'")
            db.commit();db.close();index=root/'work'/'index.sqlite'
            digest=bench.fingerprint(index)
            a=bench.replay(index);b=bench.replay(index)
            self.assertEqual(a['plan'],b['plan']);self.assertTrue(a['plan'])
            self.assertIsNone(a['duplicate_ratio']);self.assertEqual(digest,bench.fingerprint(index))
            with self.assertRaises(ValueError):bench.compare({'manifest_id':'a'},{'manifest_id':'b'})

    def test_failure_report_and_source_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'media'/'a.mp4';source.parent.mkdir();source.write_bytes(b'x')
            data=bench.manifest([source])
            with self.assertRaises(ValueError):bench.safe_output(source.parent/'out', data)
            with patch.object(core,'scan',side_effect=RuntimeError('missing ffprobe')):
                result=bench.run(data,root/'result')
            self.assertEqual(result['status'],'failed')
            self.assertEqual(source.read_bytes(),b'x')
            self.assertTrue((root/'result'/'report.md').is_file())
            self.assertEqual(json.loads((root/'result'/'result.json').read_text(encoding='utf-8'))['status'],'failed')
