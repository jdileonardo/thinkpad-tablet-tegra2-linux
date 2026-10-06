#!/usr/bin/env python3
"""Resolve an immutable builder ID and optionally verify the frozen ARM SDK."""
import argparse
import hashlib
import json
import os
import subprocess
import tarfile
from pathlib import Path


def digest(stream):
    return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('container')
    parser.add_argument('--sdk', action='store_true')
    parser.add_argument('--sdk-snapshot-check', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    lock = json.loads((project / 'port/image-inputs.lock.json').read_text())
    container = lock['containers'][args.container]
    if not args.sdk_snapshot_check:
        subprocess.run(['docker', 'image', 'inspect', container], check=True, stdout=subprocess.DEVNULL)
        if args.sdk:
            subprocess.run(['docker', 'run', '--rm', '--network', 'none', '-v',
                            f'{project}:/work', container, 'python3',
                            '/work/scripts/pinned_build_container.py', args.container,
                            '--sdk-snapshot-check'], check=True, stdout=subprocess.DEVNULL)
    if args.sdk_snapshot_check:
        path = project / 'build/image-inputs/sdk.tar.gz'
        with path.open('rb') as stream:
            if digest(stream) != lock['files']['build/image-inputs/sdk.tar.gz']:
                raise SystemExit('Frozen SDK archive hash differs')
        sdk = project / 'build/mesa-sysroot'
        entries = set()
        with tarfile.open(path) as archive:
            for member in archive:
                target = (sdk / member.name).absolute()
                if '..' in Path(member.name).parts or Path(member.name).is_absolute():
                    raise SystemExit('Invalid snapshot member path')
                if Path(member.name) != Path('.'):
                    entries.add(str(Path(member.name)))
                if member.issym():
                    matches = target.is_symlink() and os.readlink(target) == member.linkname
                elif member.isdir():
                    matches = target.is_dir() and not target.is_symlink()
                elif member.isfile() or member.islnk():
                    matches = target.is_file() and not target.is_symlink()
                    if matches:
                        with target.open('rb') as stream, archive.extractfile(member) as expected:
                            matches = digest(stream) == digest(expected)
                else:
                    raise SystemExit(f'Unsupported SDK snapshot entry: {member.name}')
                if not matches:
                    raise SystemExit(f'SDK differs from frozen snapshot: {member.name}')
        actual_entries = set()
        for parent, directories, files in os.walk(sdk):
            actual_entries.update(str((Path(parent) / name).relative_to(sdk))
                                  for name in directories + files)
        if actual_entries != entries:
            raise SystemExit('SDK tree contains missing or extra entries')
    print(container)


if __name__ == '__main__':
    main()
