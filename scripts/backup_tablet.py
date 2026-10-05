#!/usr/bin/env python3
"""Copy firmware partitions to the host. Never writes to a tablet block device."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--serial', required=True)
    ap.add_argument('--include-system', action='store_true')
    args = ap.parse_args()
    adb = ['adb', '-s', args.serial]

    def shell(command, root=False):
        if root:
            command = 'su -c ' + shlex.quote(command)
        result = subprocess.run(adb + ['shell', command], check=True, capture_output=True)
        text = result.stdout.decode(errors='replace').replace('\r\n', '\n').strip()
        return text

    if 'uid=0(root)' not in shell('id', root=True):
        raise SystemExit('Existing root access is required.')
    model = shell('getprop ro.product.model')
    if model != 'ThinkPad Tablet':
        raise SystemExit(f'Unexpected device: {model!r}')
    total = int(shell('cat /sys/block/mmcblk0/size', root=True))
    partition_info = {}
    for number in range(1, 11):
        path = f'/sys/block/mmcblk0/mmcblk0p{number}'
        start, size = shell(f'cat {path}/start {path}/size', root=True).splitlines()
        partition_info[number] = {'start_sector': int(start), 'sectors': int(size)}
    if partition_info[1]['start_sector'] != 20480:
        raise SystemExit('Storage layout differs from the inspected tablet; review before proceeding.')

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output = ROOT / 'backups' / f'{args.serial}-{stamp}'
    output.mkdir(parents=True, mode=0o700)
    staging = f'/data/local/tmp/thinkpad-backup-{stamp}.img'
    manifest = {
        'serial': args.serial, 'model': model, 'created_utc': stamp,
        'build': shell('getprop ro.build.display.id'),
        'disk_sectors': total, 'sector_bytes': 512,
        'partitions': partition_info, 'files': [],
        'limits': 'Not a full disk/user-data backup. Restore has not been tested.',
    }
    items = [
        ('boot-prefix.img', '/dev/block/mmcblk0', 0, partition_info[1]['start_sector']),
        ('recovery-SS.img', '/dev/block/mmcblk0p1', 0, partition_info[1]['sectors']),
        ('boot-LX.img', '/dev/block/mmcblk0p2', 0, partition_info[2]['sectors']),
        ('misc-MC.img', '/dev/block/mmcblk0p5', 0, partition_info[5]['sectors']),
        ('SC.img', '/dev/block/mmcblk0p7', 0, partition_info[7]['sectors']),
        ('persdata.img', '/dev/block/mmcblk0p9', 0, partition_info[9]['sectors']),
        ('disk-tail.img', '/dev/block/mmcblk0', total - 2048, 2048),
    ]
    if args.include_system:
        items += [('system-AP.img', '/dev/block/mmcblk0p3', 0, partition_info[3]['sectors']),
                  ('preinstall-PA.img', '/dev/block/mmcblk0p6', 0, partition_info[6]['sectors']),
                  ('update-UP.img', '/dev/block/mmcblk0p8', 0, partition_info[8]['sectors'])]
    manifest_path = output / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
    for name, device, skip, count in items:
        destination = output / name
        print(f'Backing up {name}: {count * 512:,} bytes', flush=True)
        # The only destination on the tablet is this temporary regular file.
        block_sectors = 2048 if skip % 2048 == 0 and count % 2048 == 0 else 1
        command = (f'/system/bin/dd if={device} of={staging} bs={block_sectors * 512} '
                   f'skip={skip // block_sectors} count={count // block_sectors}')
        response = shell(command, root=True)
        shell(f'chmod 644 {staging}', root=True)
        subprocess.run(adb + ['pull', staging, str(destination)], check=True)
        if destination.stat().st_size != count * 512:
            raise SystemExit(f'Incomplete backup: {destination}')
        digest = hashlib.sha256()
        with destination.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        manifest['files'].append({'name': name, 'device': device,
                                 'start_sector': skip, 'bytes': count * 512,
                                 'sha256': digest.hexdigest(), 'dd_output': response})
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
        shell(f'rm {staging}', root=True)
    (output / 'SHA256SUMS').write_text(''.join(
        f"{item['sha256']}  {item['name']}\n" for item in manifest['files']))
    print(f'Backup complete: {output}', flush=True)


if __name__ == '__main__':
    main()
