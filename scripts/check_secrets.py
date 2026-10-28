"""Scan committed/staged content without printing secrets or verifying them online."""
import argparse
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
    try:
        from detect_secrets.core.scan import scan_file
        from detect_secrets.settings import default_settings
    except ImportError:
        print('Install requirements-dev.txt before scanning; publication blocked.')
        return 1
    findings = {}
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        try:
            with default_settings() as settings:
                settings.disable_filters('detect_secrets.filters.common.is_ignored_due_to_verification_policies')
                for name in files:
                    content = subprocess.check_output(['git', 'show', (':' if args.staged else 'HEAD:') + name])
                    target = base / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
                    # Avoid CLI file discovery: Windows junctions can otherwise make
                    # a real file disappear from the scanner's relative-path list.
                    matches = list(scan_file(str(target.resolve())))
                    if matches:
                        findings[name] = [{'line_number': match.line_number, 'type': match.type} for match in matches]
        except Exception as exc:
            print('Secret scanner failed closed (' + type(exc).__name__ + '); values are hidden.')
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
