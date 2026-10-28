from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

import vlog_maker as core
from candidate_engine import scene_cuts, intervals
from benchmark_v16 import fingerprint
from qt_store import load_selection, save_json_atomic


class CompatibilityTests(unittest.TestCase):
    def test_old_sqlite_and_manual_json_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);index=root/'index.sqlite'
            with closing(sqlite3.connect(index)) as db:
                db.executescript('''CREATE TABLE media(path TEXT PRIMARY KEY,kind TEXT,size INTEGER,mtime REAL,
                    duration REAL,width INTEGER,height INTEGER,error TEXT);
                    CREATE TABLE candidates(id TEXT PRIMARY KEY,path TEXT,position REAL,score REAL,
                    description TEXT,analyzed INTEGER DEFAULT 0,error TEXT);
                    INSERT INTO candidates(id,path,position,score) VALUES('old','demo.mp4',4,82);''')
                db.commit()
            selection=root/'ui_selected_v441.json'
            save_json_atomic(selection,{'candidate_ids':['old'],'trims':{'old':{'start':2,'end':5}}})
            before=fingerprint(selection)
            with closing(core.connect(root)) as db:
                self.assertEqual(db.execute('SELECT id,score FROM candidates').fetchone(),('old',82))
            self.assertEqual(fingerprint(selection),before)
            self.assertEqual(load_selection(selection),(['old'],{'old':{'start':2,'end':5}}))

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg unavailable')
    def test_scene_detection_on_actual_synthetic_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            video=Path(tmp)/'cut.mp4'
            core.command(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=black:s=160x90:r=30:d=1',
                '-f','lavfi','-i','color=white:s=160x90:r=30:d=1',
                '-filter_complex','[0:v][1:v]concat=n=2:v=1:a=0','-c:v','libx264',str(video)])
            before=fingerprint(video);cuts=scene_cuts(video)
            self.assertTrue(any(abs(c-1)<.04 for c in cuts),cuts)
            ranges=intervals(core.probe(video)[0],'scene',cuts=cuts)
            self.assertEqual(len(ranges),2)
            self.assertEqual(before,fingerprint(video))
