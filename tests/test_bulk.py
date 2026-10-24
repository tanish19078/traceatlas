"""Frozen registry rows must never trigger live identity lookups."""
import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from traceatlas import core, registry
from traceatlas.bulk import BulkRegistry
from traceatlas.audit import verify
from tests.test_traceatlas import ORG, fixture

class BulkTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def write_csv(self, rows=None):
        path=self.root/'bulk.csv'
        fields=['organisasjonsnummer','navn','organisasjonsform.kode','harRegistrertAntallAnsatte','antallAnsatte','registreringsdatoenhetsregisteret','konkurs']
        values=rows or [[ORG,'SYNTHETIC TEST COMPANY','AS','false','0','2020-01-01','false']]
        with path.open('w',newline='') as stream:
            w=csv.writer(stream);w.writerow(fields);w.writerows(values)
        return path
    def test_csv_preserves_frozen_provenance_and_missing_employee_is_not_zero(self):
        path=self.write_csv();out=self.root/'out'
        with patch.object(registry,'fetch') as fetch:
            report=core.run_batch([ORG,'974760673'],out,bulk_path=path)
            fetch.assert_not_called()
        rows=[json.loads(x) for x in (out/'profiles.jsonl').read_text().splitlines()]
        self.assertEqual(report['mode'],'bulk');self.assertFalse(rows[0]['evidence'][0]['synthetic'])
        self.assertEqual(rows[1]['state'],'not_available')
        self.assertFalse(any(c['field']=='registered_employees' for c in rows[0]['claims']))
        self.assertTrue(verify(out,expected_numbers=[ORG,'974760673'])['passed'])
    def test_gzip_is_detected_even_with_csv_extension(self):
        path=self.write_csv();path.write_bytes(gzip.compress(path.read_bytes()))
        self.assertIn(ORG,BulkRegistry(path,[ORG]).rows)
    def test_jsonl_keeps_original_record(self):
        path=self.root/'bulk.jsonl';path.write_bytes(fixture()+b'\n')
        core.run_batch([ORG],self.root/'out',bulk_path=path)
        self.assertTrue(verify(self.root/'out')['passed'])
    def test_duplicate_records_fail_closed(self):
        path=self.root/'bulk.jsonl';path.write_bytes(fixture()+b'\n'+fixture()+b'\n')
        with self.assertRaisesRegex(ValueError,'duplicate_bulk'):BulkRegistry(path,[ORG])
    def test_bulk_change_refuses_resume(self):
        path=self.write_csv();out=self.root/'out';core.run_batch([ORG],out,bulk_path=path)
        path.write_text(path.read_text().replace('2020-01-01','2021-01-01'))
        with self.assertRaisesRegex(ValueError,'configuration_changed'):core.run_batch([ORG],out,bulk_path=path,resume=True)
    def test_invalid_boolean_becomes_a_terminal_failed_row(self):
        path=self.write_csv([[ORG,'SYNTHETIC','AS','unknown','0','2020-01-01','false']])
        report=core.run_batch([ORG],self.root/'out',bulk_path=path)
        self.assertEqual(report['states']['failed'],1)
    def test_bulk_and_fixture_modes_cannot_mix(self):
        with self.assertRaisesRegex(ValueError,'mutually exclusive'):core.run_batch([ORG],self.root/'out',fixture_dir=self.root,bulk_path=self.write_csv())

    def test_large_valid_csv_field_exceeds_default_python_csv_limit(self):
        path=self.root/'large.csv'
        with path.open('w',newline='') as stream:
            w=csv.writer(stream);w.writerow(['organisasjonsnummer','navn','aktivitet']);w.writerow([ORG,'SYNTHETIC','x'*150000])
        self.assertIn(ORG,BulkRegistry(path,[ORG]).rows)
