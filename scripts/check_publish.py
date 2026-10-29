"""Fail if tracked/staged paths could publish private local files."""
import argparse
from pathlib import PurePosixPath
import subprocess
import sys

PUBLIC_FILES = {
    '.gitignore', '.gitattributes', 'README.md', 'SECURITY.md', 'PUBLISHING.md', 'LICENSE',
    'app.py', 'urls.py', 'review.py', 'semantic.py', 'source_edit.py',
    'requirements.txt', 'requirements-dev.txt', 'pyproject.toml',
    'setup.bat', 'run.bat', 'sample.csv',
    'docs/screenshots/app-before-import.png',
    'docs/screenshots/imported-library-link-actions.png',
}
PUBLIC_DIRECTORIES = {'.github', '.githooks', 'scripts', 'tests'}
PUBLIC_SUFFIXES = {'.py', '.md', '.toml', '.yml', '.yaml', '.bat', '.txt'}


def tracked_files(staged=False):
    command = ['git', 'diff', '--cached', '--name-only', '--diff-filter=ACMR', '-z'] if staged else ['git', 'ls-files', '-z']
    return subprocess.check_output(command).decode('utf-8').split('\0')[:-1]


def is_public(path):
    value = PurePosixPath(path)
    if path in PUBLIC_FILES or path == '.githooks/pre-commit':
        return True
    return (bool(value.parts) and value.parts[0] in PUBLIC_DIRECTORIES
            and value.suffix in PUBLIC_SUFFIXES
            and not any(part.startswith('.env') or part.lower() in {'private', 'data', 'credentials', 'secrets', '__pycache__'} for part in value.parts)
            and not any(word in value.name.lower() for word in ('credentials', 'secrets.json', '.local.')))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true')
    args = parser.parse_args()
    files = tracked_files(args.staged)
    rejected = [path for path in files if not is_public(path)]
    if rejected:
        print('Publication blocked: these paths are not in the public source allowlist:')
        print('\n'.join(rejected))
        print('Unstage private files. Add intentional public source files to scripts/check_publish.py after review.')
        return 1
    print(f'Publication file check passed: {len(files)} approved paths.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
