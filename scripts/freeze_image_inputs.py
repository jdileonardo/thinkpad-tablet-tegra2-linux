#!/usr/bin/env python3
"""Freeze cached rootfs/SDK and verified artifacts for offline image assembly."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
LOCK = PROJECT / 'port/image-inputs.lock.json'
IMAGES = ['thinkpad-pmbootstrap:2026-10-05', 'thinkpad-nura-build:2026-10-05',
          'thinkpad-mesa-build:2026-10-05', 'thinkpad-opentegra-build:2026-10-06']


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lock', default='port/image-inputs.lock.json')
    parser.add_argument('--xorg-module', default='build/opentegra-dri3/src/.libs/opentegra_drv.so')
    parser.add_argument('--reuse-snapshots', action='store_true')
    args = parser.parse_args()
    lock_path = (PROJECT / args.lock).resolve()
    module_path = (PROJECT / args.xorg_module).resolve()
    if not lock_path.is_relative_to(PROJECT / 'port') or not module_path.is_relative_to(PROJECT / 'build'):
        raise SystemExit('Lock must be under port/ and the module under build/')
    if lock_path.exists():
        raise SystemExit('Input lock exists; review changes before freezing another snapshot')
    previous = json.loads(LOCK.read_text()) if args.reuse_snapshots else None
    container_ids = {name: json.loads(subprocess.check_output(
        ['docker', 'image', 'inspect', name]))[0]['Id'] for name in IMAGES}
    output = PROJECT / 'build/image-inputs'
    output.mkdir(parents=True, exist_ok=True)
    snapshots = {'rootfs': 'build/pmbootstrap/chroot_rootfs_nvidia-tegra-armv7',
                 'sdk': 'build/mesa-sysroot'}
    inventories = {}
    for label, source in snapshots.items():
        archive = output / f'{label}.tar.gz'
        if archive.exists() and not args.reuse_snapshots:
            raise SystemExit(f'Refusing to replace {archive}')
        if args.reuse_snapshots:
            if digest(archive) != previous['files'][str(archive.relative_to(PROJECT))]:
                raise SystemExit(f'Snapshot differs from the previous lock: {archive}')
        else:
            subprocess.run(['docker', 'run', '--rm', '--network', 'none', '-v',
                        f'{PROJECT}:/work', container_ids[IMAGES[0]], 'sh', '-ec',
                        'tar --sort=name --numeric-owner --xattrs --acls -czf "$1" -C "$2" .',
                        'snapshot', f'/work/{archive.relative_to(PROJECT)}', f'/work/{source}'],
                           check=True)
        database = (PROJECT / source / 'lib/apk/db/installed').read_text()
        packages = []
        for entry in database.split('\n\n'):
            fields = dict(line.split(':', 1) for line in entry.splitlines() if ':' in line)
            if 'P' in fields:
                packages.append({'name': fields['P'], 'version': fields['V'],
                                 'architecture': fields.get('A'), 'checksum': fields.get('C')})
        inventory = output / f'{label}-packages.json'
        content = json.dumps(sorted(packages, key=lambda p: p['name']), indent=2) + '\n'
        if args.reuse_snapshots:
            if inventory.read_text() != content or digest(inventory) != previous['files'][str(inventory.relative_to(PROJECT))]:
                raise SystemExit(f'Installed package inventory changed: {label}')
        else:
            inventory.write_text(content)
        inventories[label] = str(inventory.relative_to(PROJECT))
    artifacts = [
        'build/image-inputs/rootfs.tar.gz', 'build/image-inputs/sdk.tar.gz',
        *inventories.values(), 'build/nura-sd-root.uuid',
        'build/linux-nura/include/config/kernel.release',
        'build/linux-nura/arch/arm/boot/zImage',
        'build/linux-nura/arch/arm/boot/dts/nvidia/tegra20-lenovo-indigo.dtb',
        'build/nura-sd-test/initramfs.cpio.gz', 'build/nura-sd-test/thinkpad-ram-payload.bin',
        'build/uboot-nura-sd/u-boot-dtb-tegra.bin',
        'build/ntrig-spi/ntrig_indigo.ko', 'build/linux-nura/drivers/input/evdev.ko',
        'build/linux-nura/drivers/hid/hid-generic.ko',
        'build/linux-nura/drivers/hid/usbhid/usbhid.ko',
        'build/linux-nura/drivers/reset/reset-gpio.ko',
        'build/linux-nura/modules.builtin', 'build/linux-nura/modules.builtin.modinfo',
        'build/input-monitor', 'build/linux-firmware/brcmfmac4329-sdio.bin',
        'build/linux-firmware/LICENCE.broadcom_bcm43xx',
        'build/stock/firmware/brcmfmac4329-sdio.txt', 'build/ram-test/reboot-into-apx',
        str(module_path.relative_to(PROJECT)),
        'build/mesa-grate-armv7.tar.gz', 'build/mesa-grate-candidate-armv7.tar.gz',
        'sources.lock.json', 'port/mesa/indigo-gpu-run',
        *[str(p.relative_to(PROJECT)) for p in sorted((PROJECT / 'port/desktop').glob('*')) if p.is_file()],
        *[str(p.relative_to(PROJECT)) for p in sorted((PROJECT / 'port').rglob('*.patch'))],
    ]
    # Only add the two tools; do not upgrade the frozen runtime's libraries.
    packages = []
    for name in ('xinput', 'xdotool'):
        matches = list((output / 'apk-overlays').glob(f'{name}-[0-9]*.apk'))
        if len(matches) != 1:
            raise SystemExit(f'Expected one pinned {name} APK')
        packages.append(str(matches[0].relative_to(PROJECT)))
    artifacts += packages
    lock = {'schema': 1, 'containers': container_ids, 'snapshots': snapshots,
            'xorg_module': str(module_path.relative_to(PROJECT)),
            'package_inventories': inventories, 'overlay_packages': packages,
            'files': {name: digest(PROJECT / name) for name in artifacts},
            'reproducibility': 'Offline assembly from frozen binary inputs; not a bit-identical or fully source-rebuilt filesystem'}
    lock_path.write_text(json.dumps(lock, indent=2) + '\n')
    print(f'Frozen {len(artifacts)} inputs in {lock_path}')


if __name__ == '__main__':
    main()
