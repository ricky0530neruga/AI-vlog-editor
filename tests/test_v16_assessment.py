import json
from pathlib import Path
import tempfile
import unittest
from assessment_v16 import validate, decode, AssessmentCache

VALID=dict(technical_quality=70,visual_interest=80,event_importance=30,category='city',description='A street.',analysis_confidence=None)


class AssessmentTests(unittest.TestCase):
    def test_strict_validation(self):
        self.assertEqual(validate(VALID),VALID)
        for change in ({'visual_interest':True},{'technical_quality':'80'},{'event_importance':101},
                       {'analysis_confidence':float('nan')},{'description':''},{'category':'bogus'}):
            with self.assertRaises(ValueError):validate(dict(VALID,**change))
        with self.assertRaises(ValueError):validate({})
        with self.assertRaises(ValueError):decode('{"category":"city","category":"food"}')

    def test_resumable_cache_and_error_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'assessments.sqlite';candidate={'id':'a','source_sha256':'hash','positions':[1.]}
            cache=AssessmentCache(path)
            bad=cache.assess(candidate,'model','digest',lambda *_:'{}')
            self.assertEqual(bad['status'],'failed');self.assertIsNone(bad['assessment']);self.assertIn('ValueError',bad['error'])
            good=cache.assess(candidate,'model','digest',lambda *_:json.dumps(VALID))
            self.assertFalse(good['cached']);cache.close();cache=AssessmentCache(path)
            def forbidden(*args):self.fail('valid cache must not call model')
            self.assertTrue(cache.assess(candidate,'model','digest',forbidden)['cached'])
            self.assertFalse(cache.assess(candidate,'model','new-digest',lambda *_:json.dumps(VALID))['cached'])
            cache.close()
            with self.assertRaises(ValueError):AssessmentCache(Path(tmp)/'index.sqlite')
