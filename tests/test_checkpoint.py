"""Crash recovery must preserve inputs and refuse corrupt evidence."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from traceatlas import core, registry
from traceatlas.audit import verify
from traceatlas.checkpoint import output_lock
from tests.test_traceatlas import ORG, fixture

class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fetcher = patch.object(registry, 'fetch', return_value=fixture())
        self.fetch = self.fetcher.start()
        self.addCleanup(self.fetcher.stop)

    def test_completed_batch_resumes_without_fetching_or_history_updates(self):
        core.run_batch([ORG, ORG], self.root)
        first = (self.root/'profiles.jsonl').read_bytes()
        self.fetch.reset_mock()
        report = core.run_batch([ORG, ORG], self.root, resume=True)
        self.fetch.assert_not_called()
        self.assertEqual(report['resumed_count'], 2)
        self.assertEqual(first, (self.root/'profiles.jsonl').read_bytes())
        self.assertTrue(verify(self.root)['passed'])

    def test_partial_batch_with_torn_final_line_fetches_only_missing_rows(self):
        core.run_batch([ORG, ORG, ORG], self.root)
        journal = self.root/'completion.jsonl'
        first = journal.read_text().splitlines()[0]
        journal.write_text(first+'\n{"incomplete":')
        self.fetch.reset_mock()
        report = core.run_batch([ORG]*3,self.root,resume=True)
        self.assertEqual(self.fetch.call_count,2)
        self.assertEqual(report['resumed_count'],1)
        self.assertTrue(verify(self.root,3)['passed'])

    def test_changed_input_or_allowlist_is_refused_before_fetch(self):
        core.run_batch([ORG],self.root)
        self.fetch.reset_mock()
        for inputs,domains in [([ORG,ORG],None),([ORG],['example.com'])]:
            with self.assertRaisesRegex(ValueError,'configuration_changed'):
                core.run_batch(inputs,self.root,allowed_domains=domains,resume=True)
        self.fetch.assert_not_called()

    def test_tampered_snapshot_cannot_be_reused(self):
        core.run_batch([ORG],self.root)
        next((self.root/'snapshots').glob('*.json')).write_text('{}')
        with self.assertRaisesRegex(ValueError,'checkpoint_invalid'):
            core.run_batch([ORG],self.root,resume=True)

    def test_malformed_complete_line_is_not_treated_as_torn_write(self):
        core.run_batch([ORG],self.root)
        (self.root/'completion.jsonl').write_text('not-json\n')
        with self.assertRaisesRegex(ValueError,'checkpoint_invalid'):
            core.run_batch([ORG],self.root,resume=True)

    def test_failed_input_is_retried(self):
        core.run_batch([ORG],self.root,budget=-1)
        report=core.run_batch([ORG],self.root,resume=True)
        self.assertEqual(report['resumed_count'],0)
        self.assertEqual(report['states']['available'],1)

    def test_same_output_directory_cannot_have_two_writers(self):
        with output_lock(self.root):
            with self.assertRaisesRegex(ValueError,'output_directory_in_use'):
                core.run_batch([ORG],self.root)
        self.assertEqual(core.run_batch([ORG],self.root)['output_count'],1)

    def test_changed_fixture_is_refused(self):
        fixtures=self.root/'fixtures';fixtures.mkdir()
        source=fixtures/(ORG+'.json');source.write_bytes(fixture())
        core.run_batch([ORG],self.root,fixture_dir=fixtures)
        source.write_bytes(fixture(antallAnsatte=99))
        with self.assertRaisesRegex(ValueError,'configuration_changed'):
            core.run_batch([ORG],self.root,fixture_dir=fixtures,resume=True)

    def test_invalid_python_api_configuration_creates_no_artifacts(self):
        for kwargs in [{'workers':0},{'timeout':float('nan')},{'budget':float('inf')}]:
            with self.assertRaises(ValueError):
                core.run_batch([ORG],self.root,**kwargs)
        self.assertFalse((self.root/'run.json').exists())
