"""Scan committed/staged content without printing secrets or verifying them online."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from check_publish import tracked_files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true')
    args = parser.parse_args()
    files = tracked_files(args.staged)
    if not files:
        print('Secret scan: no files to scan.')
        return 0
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        for name in files:
            content = subprocess.check_output(['git', 'show', (':' if args.staged else 'HEAD:') + name])
            target = base / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        result = subprocess.run([sys.executable, '-m', 'detect_secrets', 'scan', '--all-files', '--no-verify', *files], cwd=base, capture_output=True, text=True)
        if result.returncode:
            print('Secret scanner could not complete. Install requirements-dev.txt and retry; no scan output was printed.')
            return 1
        try:
            findings = json.loads(result.stdout)['results']
        except (ValueError, KeyError):
            print('Secret scanner returned an invalid result; publication blocked.')
            return 1
        if findings:
            print('Potential secrets detected; values are hidden:')
            for name, matches in findings.items():
                for match in matches:
                    print(f"{name}:{match['line_number']} ({match['type']})")
            return 1
    print(f'Secret scan passed: {len(files)} files; no candidate values sent for online verification.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
