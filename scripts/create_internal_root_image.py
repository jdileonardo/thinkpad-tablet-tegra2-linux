#!/usr/bin/env python3
"""Adapt the validated SD filesystem into an internal image; host files only."""
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import uuid
from pathlib import Path


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='build/nura-internal-20261006')
    args = parser.parse_args()
    out = (root / args.output).resolve()
    if not out.is_relative_to(root / 'build'):
        raise SystemExit('Output must be under build/')
    out.mkdir(parents=True, exist_ok=True)
    image = out / 'internal-user-area.img'
    filesystem = out / 'root.ext4'
    if image.exists() or filesystem.exists():
        raise SystemExit('Keep existing images; use a new output directory')
    source_dir = root / 'build/nura-sd-20261006-touch-watchdog'
    original_manifest = json.loads((source_dir / 'image-manifest.json').read_text())
    source_image = root / original_manifest['image']
    if digest(source_image) != original_manifest['sha256']:
        raise SystemExit('Validated SD image hash differs')
    root_uuid = str(uuid.UUID((root / 'build/internal-root.uuid').read_text().strip()))
    if root_uuid == original_manifest['root_uuid']:
        raise SystemExit('Internal filesystem must have a distinct UUID')
    initrd = root / 'build/nura-internal-test/initramfs.cpio.gz'
    init = (root / 'build/nura-internal-test/init').read_text()
    if root_uuid not in init or '*c8000600.mmc*' not in init or '*c8000400.mmc*' in init:
        raise SystemExit('Internal bootstrap does not select the intended controller/UUID')
    source_fs = source_dir / 'root.ext4'
    if shutil.disk_usage(out).free < source_fs.stat().st_blocks * 512 + 64 * 1024 * 1024:
        raise SystemExit('Insufficient space for filesystem adaptation')
    subprocess.run(['cp', '--reflink=auto', '--sparse=always', str(source_fs), str(filesystem)], check=True)
    # This extension uses UUID-seeded checksums. Remove its empty bookkeeping
    # file before changing UUID; use ordinary ext4 orphan tracking instead.
    subprocess.run(['tune2fs', '-O', '^orphan_file', str(filesystem)], check=True)
    subprocess.run(['tune2fs', '-U', root_uuid, '-L', 'INDIGO_INTERNAL', str(filesystem)], check=True)
    fstab = out / 'fstab'
    fstab.write_text(f'UUID={root_uuid} / ext4 defaults,noatime 0 1\n')
    config = out / 'extlinux.conf'
    config.write_text('DEFAULT indigo\nTIMEOUT 0\nLABEL indigo\n'
                      '  LINUX /boot/vmlinuz-indigo\n'
                      '  INITRD /boot/initramfs-indigo\n'
                      '  FDT /boot/tegra20-lenovo-indigo.dtb\n'
                      '  APPEND console=tty0 console=ttyS0,115200 panic=0 rdinit=/init '
                      'indigo_boot=extlinux-internal\n')
    entries = [(fstab, '/etc/fstab'), (config, '/boot/extlinux/extlinux.conf'),
               (initrd, '/boot/initramfs-indigo')]
    commands = out / 'debugfs-update.txt'
    commands.write_text(''.join(f'rm {target}\nwrite "{path}" {target}\n'
                                for path, target in entries))
    with (out / 'filesystem-update.log').open('w') as log:
        subprocess.run(['debugfs', '-w', '-f', str(commands), str(filesystem)], check=True,
                       stdout=log, stderr=subprocess.STDOUT)
    for source, target in entries:
        extracted = out / ('verify-' + source.name)
        subprocess.run(['debugfs', '-R', f'dump {target} {extracted}', str(filesystem)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if digest(extracted) != digest(source):
            raise SystemExit(f'Filesystem content verification failed: {target}')
    with (out / 'fsck.log').open('w') as log:
        subprocess.run(['e2fsck', '-fn', str(filesystem)], check=True,
                       stdout=log, stderr=subprocess.STDOUT)
    # Use the proven DOS/ext4 user-area arrangement, with a new filesystem
    # identity. BootROM configuration lives in separate hardware boot areas.
    header = source_image.open('rb')
    with header, image.open('wb') as target:
        first_mib = bytearray(header.read(1024 * 1024))
        # Keep SD and internal PARTUUIDs distinct when both media are present.
        struct.pack_into('<I', first_mib, 440, uuid.UUID(root_uuid).int & 0xffffffff)
        target.write(first_mib)
        target.truncate(1024 * 1024 + filesystem.stat().st_size)
    subprocess.run(['dd', f'if={filesystem}', f'of={image}', 'bs=1M', 'seek=1',
                    'conv=notrunc,sparse', 'status=none'], check=True)
    partition = subprocess.check_output(['sfdisk', '--json', str(image)], text=True)
    table = json.loads(partition)['partitiontable']
    if len(table['partitions']) != 1 or table['partitions'][0]['start'] != 2048:
        raise SystemExit('Unexpected internal image partition table')
    manifest = {'source_image': str(source_image.relative_to(root)),
                'source_image_sha256': original_manifest['sha256'],
                'root_uuid': root_uuid, 'root_controller': 'c8000600.mmc',
                'image_bytes': image.stat().st_size, 'image_sha256': digest(image),
                'filesystem_bytes': filesystem.stat().st_size,
                'filesystem_sha256': digest(filesystem), 'partition_table': table,
                'changed_files': {target: digest(source) for source, target in entries},
                'filesystem_check_passed': True, 'internal_writes_performed': False,
                'physical_internal_boot_tested': False,
                'notes': ['Cloned validated SD contents; this is a clean internal user-area candidate.',
                          'Keep the private image out of Git: it includes the existing login and Wi-Fi configuration.',
                          'The initial 4 GiB filesystem can be expanded after device write/readback verification.']}
    (out / 'image-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Created host-only internal candidate, UUID {root_uuid}; fsck/content checks passed.')


if __name__ == '__main__':
    main()
