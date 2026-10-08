"""Reject invalid CLI configurations before starting network work."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

class CliTests(unittest.TestCase):
    def run_cli(self, *arguments):
        return subprocess.run([sys.executable,'traceatlas.py',*arguments],capture_output=True,text=True)

    def test_nonfinite_budget_or_timeout_is_rejected(self):
        for option in ('--budget-seconds','--timeout'):
            for value in ('nan','inf','-inf'):
                with self.subTest(option=option,value=value):
                    result = self.run_cli('--input','missing.txt',option+'='+value)
                    self.assertEqual(result.returncode,2)
                    self.assertIn('must be positive',result.stderr)
                    self.assertNotIn('Traceback',result.stderr)

    def test_missing_input_has_a_readable_error(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.run_cli('--input',str(Path(folder)/'missing.txt'))
        self.assertEqual(result.returncode,2)
        self.assertIn('readable UTF-8',result.stderr)
        self.assertNotIn('Traceback',result.stderr)

    def test_empty_input_cannot_report_success(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'empty.txt'
            path.write_text('\n')
            result=self.run_cli('--input',str(path))
        self.assertEqual(result.returncode,2)
        self.assertIn('at least one',result.stderr)

    def test_allowlist_accepts_hostnames_only(self):
        for value in ('localhost','*.example.com','example.com/path','user@example.com'):
            with self.subTest(value=value):
                result=self.run_cli('--input','missing.txt','--allow-domain',value)
                self.assertEqual(result.returncode,2)
                self.assertIn('public HTTPS hostname',result.stderr)

if __name__ == '__main__':
    unittest.main()
