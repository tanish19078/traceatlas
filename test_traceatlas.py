"""Deterministic regression tests. All fixture values are synthetic."""
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
import traceatlas as t

ORG = '923609016'
OTHER = '974760673'


def fixture(**changes):
    value = {'organisasjonsnummer': ORG, 'navn': 'SYNTHETIC TEST COMPANY',
             'antallAnsatte': 0, 'harRegistrertAntallAnsatte': True,
             'konkurs': False, 'hjemmeside': 'example.invalid'}
    value.update(changes)
    return json.dumps(value).encode()


class ResearchTests(unittest.TestCase):
    def test_org_number_validation(self):
        self.assertTrue(t.valid_org(ORG))
        for bad in ['923609017', '123', '../secret', '９２３６０９０１６', 923609016, '']:
            self.assertFalse(t.valid_org(bad))

    def test_bad_input_never_fetches(self):
        with patch.object(t, 'fetch') as fetch:
            result, body = t.research('../secret')
        fetch.assert_not_called()
        self.assertEqual(result['state'], 'failed')

    def test_wrong_identity_publishes_no_claims(self):
        with patch.object(t, 'fetch', return_value=fixture(organisasjonsnummer=OTHER)):
            result, body = t.research(ORG)
        self.assertEqual(result['state'], 'ambiguous')
        self.assertEqual(result['claims'], [])
        self.assertIsNone(body)

    def test_absent_employee_count_is_not_zero(self):
        with patch.object(t, 'fetch', return_value=fixture(harRegistrertAntallAnsatte=False)):
            result, _ = t.research(ORG)
        self.assertNotIn('registered_employees', [c['field'] for c in result['claims']])

    def test_true_zero_and_false_are_preserved(self):
        with patch.object(t, 'fetch', return_value=fixture()):
            result, _ = t.research(ORG)
        values = {c['field']: c['value'] for c in result['claims']}
        self.assertEqual(values['registered_employees'], 0)
        self.assertIs(values['bankrupt'], False)

    def test_evidence_points_to_original_value(self):
        body = fixture()
        with patch.object(t, 'fetch', return_value=body):
            result, _ = t.research(ORG)
        for claim in result['claims']:
            self.assertEqual(claim['value'], json.loads(body)[claim['json_pointer'][1:]])
            self.assertEqual(claim['evidence_id'], t.digest(body))
        self.assertEqual(result['candidates'][0]['status'], 'unverified')
        self.assertEqual(result['availability']['website_identity']['state'], 'not_available')

    def test_http_availability_states(self):
        for code, expected in [(404,'not_available'), (403,'blocked'), (429,'blocked'), (500,'failed')]:
            with self.subTest(code=code), patch.object(t, 'fetch', side_effect=urllib.error.HTTPError(t.BASE+ORG,code,'error',{},None)):
                result, _ = t.research(ORG)
                self.assertEqual(result['state'], expected)
                self.assertEqual(result['claims'], [])

    def test_bad_json_is_contained(self):
        with patch.object(t, 'fetch', return_value=b'not-json'):
            result, _ = t.research(ORG)
        self.assertEqual(result['state'], 'failed')

    def test_validation_failure_does_not_leak_partial_claims(self):
        with patch.object(t, 'fetch', return_value=fixture(antallAnsatte=-1)):
            result, _ = t.research(ORG)
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['claims'], [])

    def test_redirects_are_not_followed(self):
        self.assertIsNone(t.NoRedirect().redirect_request(None,None,302,'',{},'http://localhost/'))


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = t.Store(self.root)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def save_fixture(self, **changes):
        with patch.object(t,'fetch',return_value=fixture(**changes)):
            result, body = t.research(ORG)
        return self.store.save(result, body)

    def test_repeat_is_idempotent(self):
        first = self.save_fixture()
        second = self.save_fixture()
        self.assertEqual(first['claims'], second['claims'])
        self.assertEqual(second['refresh']['changes'], [])
        self.assertEqual(len(list((self.root/'snapshots').glob('*.json'))), 1)

    def test_real_change_retains_both_evidence_refs(self):
        self.save_fixture()
        result = self.save_fixture(antallAnsatte=8)
        change = result['refresh']['changes'][0]
        self.assertEqual(change['field'], 'registered_employees')
        self.assertEqual(change['before']['value'], 0)
        self.assertEqual(change['after']['value'], 8)
        for side in ['before','after']:
            self.assertTrue((self.root/'snapshots'/(change[side]['evidence_id']+'.json')).exists())

    def test_failed_refresh_preserves_last_success(self):
        self.save_fixture()
        result = self.store.save(t.envelope(ORG,'blocked','http_403'), None)
        self.assertTrue(result['last_known']['claims'])
        self.assertEqual(result['claims'], [])
        self.assertEqual(result['state'], 'blocked')
        self.assertEqual(self.save_fixture()['refresh']['changes'], [])

    def test_disappearing_field_is_not_asserted_as_real_world_removal(self):
        self.save_fixture()
        result = self.save_fixture(harRegistrertAntallAnsatte=False)
        self.assertEqual(result['refresh']['changes'][0]['kind'], 'no_longer_reported')

    def test_corrupted_snapshot_is_detected(self):
        self.save_fixture()
        next((self.root/'snapshots').glob('*.json')).write_text('corrupted')
        with self.assertRaisesRegex(ValueError,'integrity'):
            self.save_fixture()


class BatchTests(unittest.TestCase):
    def test_every_input_including_duplicate_and_invalid_returns(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(t,'fetch',return_value=fixture()):
            report = t.run_batch([ORG, 'bad', ORG], folder)
            lines = [json.loads(x) for x in (Path(folder)/'profiles.jsonl').read_text().splitlines()]
            self.assertEqual([x['organisation_number'] for x in lines], [ORG,'bad',ORG])
            self.assertEqual(report['output_count'], 3)
            self.assertIsNone(report['official_score'])
            self.assertEqual(report['states']['failed'], 1)

    def test_exhausted_budget_still_returns_all_results(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(t,'fetch') as fetch:
            report = t.run_batch([ORG]*3, folder, budget=-1)
        fetch.assert_not_called()
        self.assertEqual(report['states']['failed'], 3)

    def test_viewer_escapes_source_text(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(t,'fetch',return_value=fixture(navn='<script>alert(1)</script>')):
            t.run_batch([ORG], folder)
            page = (Path(folder)/'index.html').read_text()
        self.assertNotIn('<script>',page)
        self.assertIn('&lt;script&gt;',page)

    def test_fixture_mode_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root/(ORG+'.json')).write_bytes(fixture())
            report = t.run_batch([ORG], root/'out', fixture_dir=root)
            result = json.loads((root/'out'/'profiles.jsonl').read_text())
            self.assertEqual(report['mode'], 'fixture')
            self.assertTrue(result['evidence'][0]['synthetic'])

    def test_jsonl_and_text_inputs(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'input.txt'
            path.write_text(ORG+'\n'+json.dumps({'organisation_number':ORG})+'\n"bad"\n\n')
            self.assertEqual(t.read_inputs(path), [ORG,ORG,'bad'])


if __name__ == '__main__':
    unittest.main()
