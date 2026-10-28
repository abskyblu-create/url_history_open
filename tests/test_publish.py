import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.check_publish import is_public


class PublicationTests(unittest.TestCase):
    def test_private_files_are_rejected_even_if_force_added(self):
        for name in ('.env', 'input.csv', 'data/library.xlsx', '.reviews/session.json',
                     '.semantic/vectors.sqlite', '.venv/pyvenv.cfg', 'backup.xlsx.bak',
                     '.aws/credentials', 'private-key.pem', '.tools/github_auth_check.py'):
            with self.subTest(name=name):
                self.assertFalse(is_public(name))
        for name in ('app.py', 'sample.csv', '.github/workflows/health-checks.yml',
                     'tests/test_publish.py', 'scripts/check_secrets.py'):
            self.assertTrue(is_public(name))

    @unittest.skipUnless(importlib.util.find_spec('detect_secrets'), 'Install requirements-dev.txt for secret-scanner tests')
    def test_secret_scan_checks_index_and_never_prints_candidate(self):
        script = Path(__file__).resolve().parents[1] / 'scripts/check_secrets.py'
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(['git', 'init', '-q', directory], check=True)
            path = Path(directory) / 'app.py'
            candidate = 'ghp_' + hashlib.sha256(b'synthetic-test-only').hexdigest()[:36]
            path.write_text('access_value = ' + repr(candidate) + '\n', encoding='utf-8')
            subprocess.run(['git', 'add', 'app.py'], cwd=directory, check=True)
            path.write_text('# Safe working copy differs from the staged version\n', encoding='utf-8')
            result = subprocess.run([sys.executable, str(script), '--staged'], cwd=directory, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('Potential secrets detected', result.stdout)
            self.assertNotIn(candidate, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
