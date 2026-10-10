"""Reject counterfeit provenance, historical corruption and deadline overruns."""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from traceatlas import core, registry, web
from traceatlas.audit import verify
from traceatlas.models import canonical
from tests.test_traceatlas import ORG, fixture

class AuditHardeningTests(unittest.TestCase):
    def run_and_mutate(self, mutate):
        with tempfile.TemporaryDirectory() as folder, patch.object(registry,'fetch',return_value=fixture()):
            core.run_batch([ORG,ORG],folder)
            path=Path(folder)/'profiles.jsonl'
            rows=[json.loads(line) for line in path.read_text().splitlines()]
            mutate(rows)
            path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
            return verify(folder)

    def test_duplicate_input_indices_are_rejected(self):
        result=self.run_and_mutate(lambda rows:rows[1].update(input_index=0))
        self.assertFalse(result['passed'])

    def test_retrieval_dates_require_timezone(self):
        for stamp in ['unknown','2026-10-10T12:00:00']:
            with self.subTest(stamp=stamp):
                result=self.run_and_mutate(lambda rows:rows[0]['evidence'][0].update(retrieved_at=stamp))
                self.assertFalse(result['passed'])

    def test_claim_ids_are_recomputed(self):
        result=self.run_and_mutate(lambda rows:rows[0]['claims'][0].update(id='fake'))
        self.assertFalse(result['passed'])

    def test_independent_input_identities_are_checked(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(registry,'fetch',return_value=fixture()):
            core.run_batch([ORG,'invalid'],folder)
            self.assertTrue(verify(folder,expected_numbers=[ORG,'invalid'])['passed'])
            self.assertFalse(verify(folder,expected_numbers=['invalid',ORG])['passed'])

    def test_historical_claim_corruption_is_rejected_after_failed_refresh(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(registry,'fetch',return_value=fixture()):
            core.run_batch([ORG],folder)
            core.run_batch([ORG],folder,budget=-1)
            self.assertTrue(verify(folder)['passed'])
            path=Path(folder)/'profiles.jsonl';row=json.loads(path.read_text())
            row['last_known']['claims'][0]['value']='False historical claim'
            path.write_text(json.dumps(row)+'\n')
            self.assertFalse(verify(folder)['passed'])

    def test_non_utf8_export_returns_a_failed_audit(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder)/'profiles.jsonl').write_bytes(b'\xff')
            self.assertFalse(verify(folder)['passed'])

    def test_symlink_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(registry,'fetch',return_value=fixture()):
            core.run_batch([ORG],folder)
            path=next((Path(folder)/'snapshots').glob('*.json'))
            original=Path(folder)/'elsewhere.json';original.write_bytes(path.read_bytes())
            path.unlink();path.symlink_to(original)
            self.assertFalse(verify(folder)['passed'])

    def test_nonfinite_numbers_cannot_be_serialized_as_evidence(self):
        with self.assertRaises(ValueError):
            canonical({'invented_value':float('nan')})

    def test_identity_anchor_cannot_be_removed(self):
        result=self.run_and_mutate(lambda rows:rows[0].update(claims=[c for c in rows[0]['claims'] if c['field']!='legal_name']))
        self.assertFalse(result['passed'])

class RequestDeadlineTests(unittest.TestCase):
    def test_busy_host_lock_expires_without_request(self):
        session=web.SiteSession.__new__(web.SiteSession)
        gate=threading.Lock();gate.acquire()
        session.gate=[gate,0.0,1.0];session.requests=0;session.limit=5
        session.deadline=time.monotonic()+0.02
        with self.assertRaisesRegex(web.AccessError,'deadline_exhausted'):
            session._get('https://example.com/')
        self.assertEqual(session.requests,0)
        gate.release()
