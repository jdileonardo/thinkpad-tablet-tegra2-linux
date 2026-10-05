#!/usr/bin/env python3
"""Bundle U-Boot, Linux and diagnostic initramfs for one APX RAM download."""
import hashlib
import json
import argparse
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--profile', choices=['historical', 'nura', 'nura-sd'], default='historical')
args = parser.parse_args()
out = root / {'historical': 'build/ram-test', 'nura': 'build/nura-ram-test',
              'nura-sd': 'build/nura-sd-test'}[args.profile]
load_address = 0x108000
components = [
    ('uboot', 0x108000, root / 'build/uboot-direct/u-boot-dtb-tegra.bin'),
    ('kernel', 0x01000000, root / 'build/linux-historical/arch/arm/boot/zImage'),
    ('initramfs', 0x02000000, out / 'initramfs.cpio.gz'),
    ('dtb', 0x02200000, root / 'build/linux-historical/arch/arm/boot/dts/tegra20-lenovo-indigo.dtb'),
]
if args.profile != 'historical':
    uboot_dir = 'uboot-nura-sd' if args.profile == 'nura-sd' else 'uboot-nura'
    components = [
        ('uboot', 0x108000, root / f'build/{uboot_dir}/u-boot-dtb-tegra.bin'),
        ('kernel', 0x01000000, root / 'build/linux-nura/arch/arm/boot/zImage'),
        ('initramfs', 0x02400000, out / 'initramfs.cpio.gz'),
        ('dtb', 0x02600000, root / 'build/linux-nura/arch/arm/boot/dts/nvidia/tegra20-lenovo-indigo.dtb'),
    ]
    symbols = {}
    for line in (root / 'build/linux-nura/System.map').read_text().splitlines():
        address, kind, symbol = line.split()
        if symbol in ('_text', '_end'):
            symbols[symbol] = int(address, 16)
    # ARM relocates an overlapping compressed kernel beyond the inflated image.
    # Reserve another 1 MiB for its alignment, stack and decompressor workspace.
    decompression_end = (symbols['_end'] - symbols['_text'] + 0x8000
                         + components[1][2].stat().st_size + 0x100000)
    if decompression_end >= components[2][1]:
        raise SystemExit('Relocated ARM decompressor would overlap the initramfs')
image = bytearray()
manifest = {'profile': args.profile, 'load_address': hex(load_address), 'components': []}
for name, address, path in components:
    data = path.read_bytes()
    offset = address - load_address
    if len(image) > offset:
        raise SystemExit(f'Component overlap before {name}')
    image.extend(bytes(offset - len(image)))
    image.extend(data)
    manifest['components'].append(dict(name=name, address=hex(address), size=len(data),
                                     sha256=hashlib.sha256(data).hexdigest(),
                                     path=str(path.relative_to(root))))
if args.profile != 'historical' and load_address + len(image) >= 0x02800000:
    raise SystemExit('RAM download would cross the historical U-Boot startup stack')
target = out / 'thinkpad-ram-payload.bin'
target.write_bytes(image)
manifest['sha256'] = hashlib.sha256(image).hexdigest()
(out / 'payload-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(f'Wrote {target} ({len(image)} bytes); no storage-writing boot commands.')
