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

    def test_claim_span_uses_the_claim_locator_not_the_source_prefix(self):
        source={'padding':'x'*3000,'organisasjonsnummer':ORG,
                'navn':'SYNTHETIC TEST COMPANY','organisasjonsform':{'kode':'AS'},
                'harRegistrertAntallAnsatte':True,'antallAnsatte':7,'konkurs':False}
        body=json.dumps(source).encode()
        with tempfile.TemporaryDirectory() as folder,patch.object(registry,'fetch',return_value=body):
            core.run_batch([ORG],folder)
            row=json.loads((Path(folder)/'envelopes.jsonl').read_text())
            evidence=next(item for item in row['evidence']
                          if item['native_source_class']=='official_registry')
            self.assertIn('SYNTHETIC TEST COMPANY',evidence['claim_span'])
            self.assertIn('7',evidence['claim_span'])
            self.assertNotIn('x'*100,evidence['claim_span'])
    def test_resume_does_not_claim_cached_requests_as_new(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(registry,'fetch',return_value=fixture()):
            core.run_batch([ORG],folder)
            report=core.run_batch([ORG],folder,resume=True,run_id='resumed')
            row=json.loads((Path(folder)/'envelopes.jsonl').read_text())
            self.assertEqual(row['operations']['requests'],0)
            self.assertIn('reused_evidence_as_of',row['run'])
            self.assertEqual(report['requests'],0)

    def test_refresh_changes_include_resolvable_prior_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(registry,'fetch',return_value=fixture()):
                core.run_batch([ORG],folder)
            with patch.object(registry,'fetch',return_value=fixture(antallAnsatte=8)):
                core.run_batch([ORG],folder)
            row=json.loads((Path(folder)/'envelopes.jsonl').read_text())
            refs={item['id'] for item in row['evidence']}
            change=next(item for item in row['changes'] if item['field']=='registered_employees')
            self.assertIn(change['before']['evidence_id'],refs)
            self.assertIn(change['after']['evidence_id'],refs)
            self.assertTrue(validate([row],[ORG])['passed'])
            self.assertTrue(verify(folder)['passed'])

    def test_failed_refresh_exports_last_known_evidence(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(registry,'fetch',return_value=fixture()):
            core.run_batch([ORG],folder)
            core.run_batch([ORG],folder,budget=-1)
            row=json.loads((Path(folder)/'envelopes.jsonl').read_text())
            refs={item['id'] for item in row['evidence']}
            self.assertTrue(row['last_known']['claims'])
            self.assertLessEqual(set(row['last_known']['evidence_ids']),refs)
            self.assertTrue(all(item['evidence_id'] in refs for item in row['last_known']['claims']))
            self.assertTrue(validate([row],[ORG])['passed'])
