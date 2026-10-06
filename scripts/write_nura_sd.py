#!/usr/bin/env python3
"""Write the checked Nura image to an explicitly identified removable USB disk."""
import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--device', required=True)
parser.add_argument('--expected-serial', required=True)
parser.add_argument('--expected-size', type=int, required=True)
parser.add_argument('--manifest', default='build/nura-sd/image-manifest.json')
parser.add_argument('--container', action='store_true', help=argparse.SUPPRESS)
args = parser.parse_args()
project = Path(__file__).resolve().parents[1]
manifest_path = (project / args.manifest).resolve()
if not manifest_path.is_relative_to(project / 'build'):
    raise SystemExit('Image manifest must be under build/')
manifest = json.loads(manifest_path.read_text())
image = (project / manifest['image']).resolve()
if not image.is_relative_to(project / 'build'):
    raise SystemExit('Image must be under build/')

if not args.container:
    listing = json.loads(subprocess.check_output([
        'lsblk', '-bJ', '-o', 'NAME,PATH,SIZE,MODEL,SERIAL,RM,TYPE,MOUNTPOINTS,TRAN'], text=True))
    disk = next((d for d in listing['blockdevices'] if d['path'] == args.device), None)
    if not disk or disk['type'] != 'disk' or not disk['rm'] or disk['tran'] != 'usb':
        raise SystemExit('Target must be a removable whole USB disk.')
    if disk['serial'] != args.expected_serial or disk['size'] != args.expected_size:
        raise SystemExit('Fresh disk identity does not match the requested target.')
    if disk['model'].strip() != 'USB3.0 CRW -SD':
        raise SystemExit('Unexpected card reader model.')
    for node in [disk, *disk.get('children', [])]:
        if any(node.get('mountpoints') or []):
            raise SystemExit('Target or one of its partitions is mounted.')
    partition = next((d for d in disk.get('children', []) if d['path'] == args.device + '1'), None)
    if not partition:
        raise SystemExit('Expected first partition node is missing.')
    with image.open('rb') as source:
        if hashlib.file_digest(source, 'sha256').hexdigest() != manifest['sha256']:
            raise SystemExit('Source image SHA256 differs from the checked manifest.')
    print(f'Writing {manifest["size"]} checked bytes to {args.device}: '
          f'{disk["model"].strip()}, serial {disk["serial"]}, {disk["size"]} bytes.', flush=True)
    subprocess.run([
        'docker', 'run', '--rm', '--network', 'none', '--cap-add', 'SYS_ADMIN',
        '--security-opt', 'apparmor=unconfined',
        '--device', f'{args.device}:/dev/card:rwm',
        '--device', f'{partition["path"]}:/dev/cardp1:rwm',
        '-v', f'{project}:/work', manifest.get('assembler_container', 'thinkpad-pmbootstrap:2026-10-05'),
        'python3', '/work/scripts/write_nura_sd.py', '--container',
        '--device', '/dev/card', '--expected-serial', args.expected_serial,
        '--expected-size', str(args.expected_size),
        '--manifest', str(manifest_path.relative_to(project))], check=True)
    raise SystemExit(0)

size = int(subprocess.check_output(['blockdev', '--getsize64', '/dev/card']))
if size != args.expected_size or image.stat().st_size != manifest['size'] or size < manifest['size']:
    raise SystemExit('Container block size or source image length differs from the verified target.')
with image.open('rb') as source:
    if hashlib.file_digest(source, 'sha256').hexdigest() != manifest['sha256']:
        raise SystemExit('Source image changed before writing; refusing to erase the card.')
subprocess.run(['wipefs', '--all', '--force', '/dev/card'], check=True)
started = time.monotonic()
with image.open('rb') as source, open('/dev/card', 'r+b', buffering=0) as target:
    written = 0
    while block := source.read(8 * 1024 * 1024):
        view = memoryview(block)
        while view:
            count = target.write(view)
            if not count:
                raise OSError('Short write to SD card')
            view = view[count:]
        written += len(block)
        if written % (128 * 1024 * 1024) == 0:
            print(f'Write {written // (1024 * 1024)}/{manifest["size"] // (1024 * 1024)} MiB', flush=True)
    os.fsync(target.fileno())
subprocess.run(['blockdev', '--flushbufs', '/dev/card'], check=True)
print('Write complete; checking every written byte from the card.', flush=True)
digest = hashlib.sha256()
remaining = manifest['size']
with open('/dev/card', 'rb', buffering=0) as card:
    while remaining:
        data = card.read(min(8 * 1024 * 1024, remaining))
        if not data:
            raise OSError('Short read from SD card')
        digest.update(data)
        remaining -= len(data)
if digest.hexdigest() != manifest['sha256']:
    raise SystemExit('Card read-back SHA256 does not match the source image.')
print(f'Full card-image read-back verified: {digest.hexdigest()}', flush=True)
# Extend partition and filesystem only after verifying the original image.
subprocess.run(['sfdisk', '--force', '/dev/card'],
               input='label: dos\nunit: sectors\n\nstart=2048, type=83, bootable\n',
               text=True, check=True)
subprocess.run(['blockdev', '--rereadpt', '/dev/card'], check=True)
result = subprocess.run(['e2fsck', '-f', '-p', '/dev/cardp1'])
if result.returncode not in (0, 1):
    raise SystemExit('Pre-resize filesystem check failed.')
subprocess.run(['resize2fs', '/dev/cardp1'], check=True)
subprocess.run(['e2fsck', '-f', '-n', '/dev/cardp1'], check=True)
subprocess.run(['blockdev', '--flushbufs', '/dev/card'], check=True)
record = dict(manifest)
record.update(card_size=size, reader_serial=args.expected_serial,
              full_image_readback_sha256=digest.hexdigest(),
              final_verification='expanded ext4 filesystem passed e2fsck -fn',
              elapsed_seconds=round(time.monotonic() - started, 1))
(manifest_path.parent / 'card-write-verification.json').write_text(json.dumps(record, indent=2) + '\n')
print('Nura SD card write, full read-back, expansion and filesystem checks complete.', flush=True)
