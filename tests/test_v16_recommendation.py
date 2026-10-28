import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from recommendation_v16 import recommend
from test_v16_assessment import VALID


def candidate(key,path='a',start=0):
    return dict(id=key,path=path,kind='video',start=start,end=start+8,source_duration=30,
                analysis=dict(status='ok',assessment=VALID),technical={})


class RecommendationTests(unittest.TestCase):
    def test_determinism_bounds_diversity_and_exclusion(self):
        rows=[candidate('1'),candidate('2','a',10),candidate('3','b'),candidate('4','c')]
        a=recommend(rows,11,excluded_ids=['4'])
        self.assertEqual(a,recommend(list(reversed(rows)),11,excluded_ids=['4']))
        self.assertEqual(a['selection_seconds'],11)
        self.assertEqual([p['path'] for p in a['plan'][:2]],['a','b'])
        self.assertNotIn('4',[p['candidate_id'] for p in a['plan']])
        self.assertTrue(all(p['start']>=p['scene_start'] and p['start']+p['seconds']<=p['scene_end'] for p in a['plan']))

    def test_manual_locks_preserved_and_failure_not_promoted(self):
        manual=[dict(candidate_id='manual',path='manual',start=1,seconds=7,trim_locked=True)]
        original=copy.deepcopy(manual)
        rows=[candidate('bad')];rows[0]['analysis']={'status':'failed','assessment':None}
        result=recommend(rows,5,existing=manual)
        self.assertEqual(result['plan'],original);self.assertEqual(manual,original)
        self.assertEqual(result['overrun_seconds'],2)

    def test_qt_recommend_keeps_existing_order_and_trims(self):
        try: from vlog_qt import EditorWindow
        except ImportError:self.skipTest('PySide6 unavailable')
        from types import SimpleNamespace
        from contextlib import nullcontext
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'index.sqlite').touch()
            obj=SimpleNamespace(workspace_dir=root,selected_ids=['manual'],manual_trims={'manual':{'start':1,'end':3}},
                                get_length=lambda:10,min_score_box=SimpleNamespace(currentText=lambda:'40'),
                                persist_selection=lambda:None,refresh_plan=lambda:None,notice=lambda *args:None)
            with patch('vlog_qt.store.readonly_db',return_value=MagicMock()),patch('vlog_maker.choose',return_value=[{'candidate_id':'suggested'}]):
                self.assertTrue(EditorWindow.recommend(obj))
            self.assertEqual(obj.selected_ids,['manual'])
            self.assertEqual(obj.manual_trims,{'manual':{'start':1,'end':3}})
            self.assertTrue((root/'ai_recommendation_preview_v16.json').is_file())
