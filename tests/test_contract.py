"""Contract output stays separate from native auditable profiles."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from traceatlas import core,registry
from traceatlas.contract import validate
from traceatlas.audit import verify
from tests.test_traceatlas import ORG,fixture

class ContractTests(unittest.TestCase):
    def test_every_input_gets_terminal_contract_including_failure(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(registry,'fetch',return_value=fixture()):
            report=core.run_batch([ORG,'invalid'],folder,run_id='audit-fix')
            rows=[json.loads(s) for s in (Path(folder)/'envelopes.jsonl').read_text().splitlines()]
            self.assertTrue(validate(rows,[ORG,'invalid'])['passed'])
            self.assertEqual(rows[1]['run']['terminal_status'],'failed')
            self.assertEqual(rows[0]['run']['run_id'],'audit-fix')
            self.assertTrue(report['contract_validation']['passed'])
            self.assertTrue(verify(folder)['passed'])
            self.assertIn('claim_span',rows[0]['evidence'][0])
    def test_tampered_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(registry,'fetch',return_value=fixture()):
            core.run_batch([ORG],folder)
            row=json.loads((Path(folder)/'envelopes.jsonl').read_text())
            for mutate in [lambda r:r['claims'][0].update(evidence_ids=['missing']),lambda r:r['operations'].update(requests=-1),lambda r:r['run'].update(completed_at='no date')]:
                bad=copy.deepcopy(row);mutate(bad);self.assertFalse(validate([bad],[ORG])['passed'])
    def test_resume_does_not_claim_cached_requests_as_new(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(registry,'fetch',return_value=fixture()):
            core.run_batch([ORG],folder)
            report=core.run_batch([ORG],folder,resume=True,run_id='resumed')
            row=json.loads((Path(folder)/'envelopes.jsonl').read_text())
            self.assertEqual(row['operations']['requests'],0)
            self.assertIn('reused_evidence_as_of',row['run'])
            self.assertEqual(report['requests'],0)
