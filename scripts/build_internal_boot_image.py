#!/usr/bin/env python3
"""Package a board-specific Tegra20 boot image on the host; never open a device."""
import argparse
import hashlib
import json
import struct
import subprocess
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='build/internal-boot-20261006')
    args = parser.parse_args()
    out = (root / args.output).resolve()
    if not out.is_relative_to(root / 'build'):
        raise SystemExit('Output must be under build/')
    out.mkdir(parents=True, exist_ok=True)
    target = out / 'boot-region.img'
    if target.exists():
        raise SystemExit('Keep the existing boot image; use a new output directory')
    source = root / 'sources/cbootimage'
    expected = json.loads((root / 'sources.lock.json').read_text())['cbootimage']['commit']
    actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if actual != expected:
        raise SystemExit('cbootimage source revision differs from source lock')
    original_path = root / 'backups/MP0GKR7-20261005T160450Z/active.bct'
    original = original_path.read_bytes()
    if sha(original) != '3d089f88af9ffaf2dec929c2b27e02d63da70b186548bdcffb95e1477beb9421':
        raise SystemExit('Original board BCT hash differs')
    uboot = root / 'build/uboot-nura-extlinux/u-boot-dtb-tegra.bin'
    # Obtain ABI offsets from the pinned NVIDIA header rather than hand-copying
    # offsets or regenerating board-specific customer data from text.
    fields = ['crypto_hash', 'badblock_table', 'bootloader_used', 'bootloader',
              'reserved', 'customer_data', 'sdram_params', 'dev_params', 'odm_data']
    c = '#include <stdint.h>\n#include <stddef.h>\n#include <stdio.h>\n'
    c += '#include "t20/nvboot_bct_t20.h"\nint main(void) {\n'
    c += 'printf("size %zu\\n", sizeof(nvboot_config_table));\n'
    for field in fields:
        c += (f'printf("{field} %zu %zu\\n", offsetof(nvboot_config_table, {field}), '
              f'sizeof(((nvboot_config_table *)0)->{field}));\n')
    c += 'return 0; }\n'
    (out / 'bct-layout.c').write_text(c)
    subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror', '-I', str(source / 'src'),
                    str(out / 'bct-layout.c'), '-o', str(out / 'bct-layout')], check=True)
    lines = subprocess.check_output([str(out / 'bct-layout')], text=True).splitlines()
    if int(lines[0].split()[1]) != len(original) or len(original) != 4080:
        raise SystemExit('Unexpected Tegra20 BCT ABI')
    layout = {line.split()[0]: list(map(int, line.split()[1:])) for line in lines[1:]}
    template = bytearray(original)
    for field in ['bootloader_used', 'bootloader']:
        offset, size = layout[field]
        template[offset:offset + size] = bytes(size)
    template_path = out / 'board-without-old-bootloaders.bct'
    template_path.write_bytes(template)
    config = out / 'boot-image.cfg'
    config.write_text(f'Bctfile = {template_path};\nVersion = 5;\nBctcopy = 2;\n'
                      f'Redundancy = 2;\nBootLoader = {uboot}, 0x108000, 0x108000, Complete;\n')
    with (out / 'cbootimage.log').open('w') as log:
        subprocess.run([str(source / 'src/cbootimage'), '-t', '20', str(config), str(target)],
                       check=True, stdout=log, stderr=subprocess.STDOUT)
    image = target.read_bytes()
    if len(image) > 2097152:
        raise SystemExit('Generated image does not fit one hardware boot area')
    bct = image[:4080]
    changed = {i for i, (a, b) in enumerate(zip(original, bct)) if a != b}
    allowed = set()
    for field in ['crypto_hash', 'badblock_table', 'bootloader_used', 'bootloader', 'reserved']:
        offset, size = layout[field]
        allowed.update(range(offset, offset + size))
    if changed - allowed:
        raise SystemExit('Generated image unexpectedly changed board configuration bytes')
    count_offset = layout['bootloader_used'][0]
    if struct.unpack_from('<I', bct, count_offset)[0] != 2:
        raise SystemExit('Expected exactly two new bootloader descriptors')
    if image[16384:16384 + 4080] != bct:
        raise SystemExit('Second BCT copy differs')
    def cmac(data):
        result = subprocess.check_output([
            'openssl', 'mac', '-macopt', 'cipher:AES-128-CBC',
            '-macopt', 'hexkey:' + '0' * 32, 'CMAC'], input=data)
        return bytes.fromhex(result.decode().strip())

    if cmac(bct[16:]) != bct[:16]:
        raise SystemExit('Independent BCT AES-CMAC check failed')
    uboot_data = uboot.read_bytes()
    descriptor_size = layout['bootloader'][1] // 4
    copies = []
    for i in range(2):
        offset = layout['bootloader'][0] + i * descriptor_size
        version, block, page, length, load, entry, attributes = struct.unpack_from('<7I', bct, offset)
        start = block * 16384 + page * 512
        if (length != len(uboot_data) or image[start:start + length] != uboot_data or
                version != 5 or load != 0x108000 or entry != 0x108000 or
                cmac(uboot_data) != bct[offset + 28:offset + 44]):
            raise SystemExit('Bootloader descriptor/content/CMAC check failed')
        copies.append({'offset': start, 'bytes': length, 'version': version})
    new_bct = out / 'boot.bct'
    new_bct.write_bytes(bct)
    dump = subprocess.check_output([str(source / 'src/bct_dump'), str(new_bct)], text=True)
    (out / 'boot-bct-decoded.txt').write_text(dump)
    (out / 'boot-region-padded.img').write_bytes(image + bytes(2097152 - len(image)))
    manifest = {'cbootimage_source_revision': actual, 'original_bct_sha256': sha(original),
                'uboot_sha256': sha(uboot.read_bytes()), 'uboot_bytes': uboot.stat().st_size,
                'image_bytes': len(image), 'image_sha256': sha(image),
                'bct_sha256': sha(bct), 'bct_copies': 2, 'bootloader_copies': 2,
                'padded_image_bytes': 2097152,
                'padded_image_sha256': sha((out / 'boot-region-padded.img').read_bytes()),
                'bct_layout': layout, 'board_parameters_byte_preserved': True,
                'bootloader_copy_ranges': copies,
                'bct_and_bootloader_cmac_independently_verified': True,
                'old_bootloader_descriptors_removed': True,
                'internal_writes_performed': False, 'rom_cold_boot_tested': False,
                'notes': ['Host packaging only; no target boot region or MMC configuration has been written.',
                          'Validate BCT through APX and complete bounded write/recovery planning before installation.']}
    (out / 'boot-image-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Packaged {len(image)} bytes with preserved board parameters; no device writes.')


if __name__ == '__main__':
    main()
