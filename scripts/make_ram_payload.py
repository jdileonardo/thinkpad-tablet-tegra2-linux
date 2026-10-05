#!/usr/bin/env python3
"""Bundle U-Boot, Linux and diagnostic initramfs for one APX RAM download."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = root / 'build/ram-test'
load_address = 0x108000
components = [
    ('uboot', 0x108000, root / 'build/uboot-direct/u-boot-dtb-tegra.bin'),
    ('kernel', 0x01000000, root / 'build/linux-historical/arch/arm/boot/zImage'),
    ('initramfs', 0x02000000, out / 'initramfs.cpio.gz'),
    ('dtb', 0x02200000, root / 'build/linux-historical/arch/arm/boot/dts/tegra20-lenovo-indigo.dtb'),
]
image = bytearray()
manifest = {'load_address': hex(load_address), 'components': []}
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
target = out / 'thinkpad-ram-payload.bin'
target.write_bytes(image)
manifest['sha256'] = hashlib.sha256(image).hexdigest()
(out / 'payload-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(f'Wrote {target} ({len(image)} bytes); no storage-writing boot commands.')
