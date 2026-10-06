#!/usr/bin/env python3
"""Apply a known Mesa patch stack without discarding unrecorded source edits."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('patch_directory', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    patches = sorted(args.patch_directory.resolve().glob('*.patch'))

    def git(*arguments, env=None):
        return subprocess.check_output(['git', '-C', str(source), *arguments], env=env)

    actual = git('diff', '--binary', 'HEAD', '--')
    # Build each expected prefix in a disposable index. Checking individual
    # patches in reverse fails when later patches modify their context lines.
    with tempfile.TemporaryDirectory(prefix='indigo-mesa-index-') as temporary:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / 'index'))
        git('read-tree', 'HEAD', env=env)
        matching_prefix = 0 if not actual else None
        for index, patch in enumerate(patches, 1):
            git('apply', '--cached', str(patch), env=env)
            expected = git('diff', '--cached', '--binary', 'HEAD', '--', env=env)
            if actual == expected:
                matching_prefix = index
    if matching_prefix is None:
        raise SystemExit('Mesa source contains edits outside the recorded patch stack; '
                         'record them in a patch before building')
    for patch in patches[matching_prefix:]:
        git('apply', str(patch))
    print(f'Verified {len(patches)} Mesa patches; applied '
          f'{len(patches) - matching_prefix} new patches')


if __name__ == '__main__':
    main()
