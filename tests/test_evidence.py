import json
import tempfile
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import traceatlas.core as traceatlas
import traceatlas.registry as registry
from traceatlas.audit import verify
from tests.test_traceatlas import ORG, fixture

class EvidenceAuditTests(unittest.TestCase):
    def test_intact_export_passes_and_tampered_value_fails(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(registry,'fetch',return_value=fixture()):
            traceatlas.run_batch([ORG], folder)
            self.assertTrue(verify(folder)['passed'])
            path = Path(folder)/'profiles.jsonl'
            row = json.loads(path.read_text())
            row['claims'][0]['value'] = 'Fabricated value'
            path.write_text(json.dumps(row)+'\n')
            self.assertFalse(verify(folder)['passed'])

    def test_tampered_source_fails_hash_check(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(registry,'fetch',return_value=fixture()):
            traceatlas.run_batch([ORG], folder)
            path = next((Path(folder)/'snapshots').glob('*.json'))
            path.write_text('{}')
            self.assertIn('snapshot hash mismatch', verify(folder)['errors'][0]['error'])

    def test_optimized_python_rejects_tampered_claim(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(registry, 'fetch', return_value=fixture()):
            traceatlas.run_batch([ORG], folder)
            path = Path(folder) / 'profiles.jsonl'
            row = json.loads(path.read_text())
            row['claims'][0]['value'] = 'Fabricated'
            path.write_text(json.dumps(row) + '\n')
            proc = subprocess.run([sys.executable, '-O', '-m', 'traceatlas.audit', folder], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 1)
            self.assertFalse(json.loads(proc.stdout)['passed'])

    def test_empty_export_and_missing_rows_fail(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(registry, 'fetch', return_value=fixture()):
            traceatlas.run_batch([ORG, ORG], folder)
            path = Path(folder) / 'profiles.jsonl'
            lines = path.read_text().splitlines()
            path.write_text(lines[0] + '\n')
            self.assertFalse(verify(folder)['passed'])
            path.write_text('')
            self.assertFalse(verify(folder)['passed'])

    def test_non_object_result_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / 'profiles.jsonl').write_text('null\n')
            self.assertFalse(verify(folder)['passed'])

if __name__ == '__main__':
    unittest.main()
