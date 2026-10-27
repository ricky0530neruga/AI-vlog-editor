import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
"""PySide-free compatibility tests for the v1.5 Qt migration."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

import qt_store
from trim_times import parse_time, validate_times


class StoreTests(unittest.TestCase):
    def test_workspace_hash_is_v14_compatible(self):
        inputs=[r'C:\Travel\a',r'C:\Travel\b']
        old=hashlib.sha256('\n'.join(sorted(os.path.normcase(p) for p in inputs)).encode('utf8')).hexdigest()[:12]
        self.assertEqual(qt_store.workspace(inputs,'test').name,'AI_Vlog_'+old)

    def test_selection_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/qt_store.SELECTION_FILE
            original={'version':'1.4','candidate_ids':['a','b'],
                      'trims':{'b':{'start':1.2,'end':4.5}}}
            qt_store.save_json_atomic(file,original)
            self.assertEqual(qt_store.load_selection(file),(['a','b'],{'b':{'start':1.2,'end':4.5}}))

    def test_invalid_json_never_crashes_loader(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'bad.json';file.write_text('[]',encoding='utf8')
            with self.assertRaises(ValueError):qt_store.load_selection(file)

    def test_candidate_filter_and_prune(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            media=folder/'clip.mp4';media.write_bytes(b'mock')
            file=folder/'index.sqlite'
            db=sqlite3.connect(file)
            db.executescript('''CREATE TABLE media(path TEXT PRIMARY KEY,kind TEXT,duration REAL,error TEXT);
            CREATE TABLE candidates(id TEXT PRIMARY KEY,path TEXT,position REAL,score REAL,event REAL,
             category TEXT,description TEXT,v2 INTEGER,error TEXT,prefilter_skip TEXT,quick_done INTEGER);''')
            db.execute('INSERT INTO media VALUES(?,?,?,?)',(str(media),'video',10.,None))
            db.execute('INSERT INTO candidates VALUES(?,?,?,?,?,?,?,?,?,?,?)',('a',str(media),4.,90.,1.,'travel','Nice',1,None,None,1))
            db.commit();db.close()
            total,ready,count,rows,stats=qt_store.candidates_page(file)
            self.assertEqual((total,ready,count,len(rows)),(1,1,1,1))
            self.assertEqual(rows[0]['display_status'],'已分析')
            ids,trims,warnings=qt_store.prune_selection(file,['a','missing'],{'a':{'start':2.,'end':5.}})
            self.assertEqual(ids,['a']);self.assertEqual(trims,{'a':{'start':2.,'end':5.}})
            self.assertEqual(len(warnings),1)
            media.unlink()
            ids,trims,warnings=qt_store.prune_selection(file,['a'],{'a':{'start':2.,'end':5.}})
            self.assertEqual(ids,[]);self.assertEqual(trims,{})

    def test_trim_time_validation(self):
        self.assertEqual(parse_time('00:12.500'),12.5)
        self.assertEqual(validate_times(1,3,10),(1.,3.))
        with self.assertRaises(ValueError):parse_time('nan')
        with self.assertRaises(ValueError):validate_times(4,3,10)


if __name__=='__main__':unittest.main()
