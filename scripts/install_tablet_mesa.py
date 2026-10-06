#!/usr/bin/env python3
"""Run on Indigo: install the staged Mesa build on the verified external SD."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import tarfile

parser = argparse.ArgumentParser()
parser.add_argument('staging', type=Path)
parser.add_argument('--revision', default='647c79415a02',
                    choices=('647c79415a02', 'ad06de32d309'))
args = parser.parse_args()
root_device = next(line.split()[0] for line in Path('/proc/mounts').read_text().splitlines()
                   if line.split()[1] == '/')
block_path = (Path('/sys/class/block') / Path(root_device).name).resolve()
if os.getuid() != 0 or 'c8000400' not in str(block_path):
    raise SystemExit(f'Refusing install outside external SD root: {root_device}, {block_path}')
expected_files = {'mesa-grate-armv7.tar.gz', 'gpu-pixel-check', 'indigo-gpu-run'}
manifest = {}
for line in (args.staging / 'SHA256SUMS').read_text().splitlines():
    digest, filename = line.split()
    manifest[filename] = digest
if set(manifest) != expected_files:
    raise SystemExit('Unexpected artifact manifest')
for filename, digest in manifest.items():
    actual = hashlib.sha256((args.staging / filename).read_bytes()).hexdigest()
    if actual != digest:
        raise SystemExit(f'SHA256 mismatch: {filename}')
prefix = 'opt/indigo-mesa/' + args.revision
with tarfile.open(args.staging / 'mesa-grate-armv7.tar.gz') as archive:
    for member in archive:
        name = member.name.removeprefix('./').rstrip('/')
        if '..' in Path(name).parts or name.startswith('/'):
            raise SystemExit(f'Unsafe archive member: {name}')
        if name not in ('opt', 'opt/indigo-mesa', prefix) and not name.startswith(prefix + '/'):
            raise SystemExit(f'Unexpected archive member: {name}')
    archive.extractall('/', filter='data')
Path('/usr/local/bin').mkdir(parents=True, exist_ok=True)
private_bin = Path('/') / prefix / 'bin'
private_bin.mkdir(exist_ok=True)
shutil.copyfile(args.staging / 'gpu-pixel-check', private_bin / 'gpu-pixel-check')
(private_bin / 'gpu-pixel-check').chmod(0o755)
for filename in ('gpu-pixel-check', 'indigo-gpu-run'):
    destination = Path('/usr/local/bin') / filename
    shutil.copyfile(args.staging / filename, destination)
    destination.chmod(0o755)
print(f'Installed private Mesa on {root_device}; run indigo-gpu-run gpu-pixel-check')
