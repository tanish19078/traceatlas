"""A stuck worker must not prevent one terminal envelope per input."""
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from traceatlas.supervisor import supervise
from traceatlas.audit import verify
from tests.test_traceatlas import ORG,fixture

class SupervisorTests(unittest.TestCase):
    def test_hung_worker_is_killed_and_every_input_is_exported(self):
        with tempfile.TemporaryDirectory() as folder:
            began=time.monotonic()
            code=supervise([sys.executable,'-c','import time;time.sleep(30)'],[ORG,'invalid'],folder,0.3,'deadline-test','live')
            self.assertLess(time.monotonic()-began,3)
            self.assertEqual(code,2)
            rows=[json.loads(line) for line in (Path(folder)/'envelopes.jsonl').read_text().splitlines()]
            self.assertEqual([r['organisation_number'] for r in rows],[ORG,'invalid'])
            self.assertTrue(all(r['state']=='failed' for r in rows))
            self.assertTrue(verify(folder,expected_numbers=[ORG,'invalid'])['passed'])
    def test_normal_worker_exit_preserves_its_valid_export(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'input.txt').write_text(ORG+'\n');(root/(ORG+'.json')).write_bytes(fixture())
            command=[sys.executable,'-m','traceatlas','--input',str(root/'input.txt'),'--fixtures',folder,'--output',str(root/'out'),'--run-id','normal']
            code=supervise(command,[ORG],root/'out',5,'normal','fixture')
            self.assertEqual(code,0);self.assertTrue(verify(root/'out')['passed'])
            self.assertNotIn('supervisor_stopped_worker',json.loads((root/'out/report.json').read_text()))
    def test_worker_crash_still_returns_every_input(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(supervise([sys.executable,'-c','raise SystemExit(1)'],[ORG],folder,2,'crashed','live'),2)
            self.assertEqual(json.loads((Path(folder)/'profiles.jsonl').read_text())['errors'],['worker_exited_before_complete_export'])

    def test_completed_checkpoint_survives_worker_termination(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/(ORG+'.json')).write_bytes(fixture());out=root/'out'
            script=f"from traceatlas.core import run_batch;import time;run_batch([{ORG!r}],{str(out)!r},fixture_dir={folder!r},run_id='partial');time.sleep(30)"
            code=supervise([sys.executable,'-c',script],[ORG,'invalid'],out,1.5,'partial','fixture')
            self.assertEqual(code,2)
            rows=[json.loads(line) for line in (out/'profiles.jsonl').read_text().splitlines()]
            self.assertEqual([r['state'] for r in rows],['available','failed'])
            self.assertTrue(verify(out,expected_numbers=[ORG,'invalid'])['passed'])
