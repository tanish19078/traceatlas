import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import traceatlas
from verify_evidence import verify
from test_traceatlas import ORG, fixture

class EvidenceAuditTests(unittest.TestCase):
    def test_intact_export_passes_and_tampered_value_fails(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(traceatlas,'fetch',return_value=fixture()):
            traceatlas.run_batch([ORG], folder)
            self.assertTrue(verify(folder)['passed'])
            path = Path(folder)/'profiles.jsonl'
            row = json.loads(path.read_text())
            row['claims'][0]['value'] = 'Fabricated value'
            path.write_text(json.dumps(row)+'\n')
            self.assertFalse(verify(folder)['passed'])

    def test_tampered_source_fails_hash_check(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(traceatlas,'fetch',return_value=fixture()):
            traceatlas.run_batch([ORG], folder)
            path = next((Path(folder)/'snapshots').glob('*.json'))
            path.write_text('{}')
            self.assertIn('snapshot hash mismatch', verify(folder)['errors'][0]['error'])

if __name__ == '__main__':
    unittest.main()
