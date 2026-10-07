#!/usr/bin/env python3
"""Prepare non-flashing boot profiles in the pinned historical U-Boot source."""
from pathlib import Path
import subprocess
import argparse
import hashlib
import json

parser = argparse.ArgumentParser()
profiles = parser.add_mutually_exclusive_group()
profiles.add_argument('--direct-linux', action='store_true')
profiles.add_argument('--nura', action='store_true')
profiles.add_argument('--nura-sd', action='store_true')
profiles.add_argument('--nura-internal', action='store_true',
                      help='APX RAM Linux with the internal-root bootstrap')
profiles.add_argument('--nura-storage-test', action='store_true',
                      help='Verify SD boot and an eMMC read, with an APX RAM fallback')
profiles.add_argument('--nura-storage', action='store_true',
                      help='Load verified boot files from SD without preloaded Linux')
profiles.add_argument('--nura-extlinux', action='store_true',
                      help='Load replaceable extlinux configuration from SD, then eMMC')
args = parser.parse_args()

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'sources/u-boot-historical'
EXPECTED = '385640388c84e405f817f8e747d4febaa0be0de5'
actual = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
if actual != EXPECTED:
    raise SystemExit(f'Expected source {EXPECTED}; found {actual}')

original = subprocess.check_output(
    ['git', '-C', str(SOURCE), 'show', 'HEAD:configs/ventana_defconfig'], text=True)
original = '\n'.join(line for line in original.splitlines() if line not in (
    'CONFIG_ENV_IS_IN_MMC=y', 'CONFIG_USB_KEYBOARD=y', 'CONFIG_CMD_EXT4_WRITE=y'))
extra = '''
CONFIG_ENV_IS_NOWHERE=y
# CONFIG_ENV_IS_IN_MMC is not set
# CONFIG_USB_KEYBOARD is not set
# CONFIG_CMD_EXT4_WRITE is not set
CONFIG_BOOTDELAY=0
CONFIG_USE_BOOTCOMMAND=y
CONFIG_BOOTCOMMAND="fastboot usb 0"
CONFIG_USB_GADGET=y
CONFIG_CI_UDC=y
CONFIG_USB_GADGET_DOWNLOAD=y
CONFIG_USB_FUNCTION_FASTBOOT=y
CONFIG_CMD_FASTBOOT=y
CONFIG_USB_GADGET_MANUFACTURER="ThinkPad RAM port"
CONFIG_USB_GADGET_VENDOR_NUM=0x17ef
CONFIG_USB_GADGET_PRODUCT_NUM=0x741c
CONFIG_FASTBOOT_BUF_ADDR=0x01000000
CONFIG_FASTBOOT_BUF_SIZE=0x08000000
# CONFIG_FASTBOOT_FLASH is not set
# CONFIG_FASTBOOT_CMD_OEM_FORMAT is not set
# CONFIG_PYLIBFDT is not set
'''
if args.direct_linux or args.nura or args.nura_sd or args.nura_internal:
    ramdisk_dir = ('build/nura-internal-test' if args.nura_internal else
                   'build/nura-sd-test' if args.nura_sd else
                   'build/nura-ram-test' if args.nura else 'build/ram-test')
    ramdisk_size = (ROOT / ramdisk_dir / 'initramfs.cpio.gz').stat().st_size
    ramdisk_addr = 0x02400000 if args.nura or args.nura_sd or args.nura_internal else 0x02000000
    dtb_addr = 0x02600000 if args.nura or args.nura_sd or args.nura_internal else 0x02200000
    boot_command = (
        'setenv bootargs console=tty0 console=ttyS0,115200 loglevel=7 '
        'panic=0 rdinit=/init; echo Starting ThinkPad diagnostic Linux from RAM; '
        f'bootz 0x01000000 0x{ramdisk_addr:08x}:0x{ramdisk_size:x} 0x{dtb_addr:08x}'
    )
    extra = extra.replace('CONFIG_BOOTCOMMAND="fastboot usb 0"',
                          f'CONFIG_BOOTCOMMAND="{boot_command}"')
config_name = 'thinkpad_ram_defconfig'
if args.nura_extlinux:
    boot_command = (
        'setenv kernel_addr_r 0x01000000; '
        'setenv ramdisk_addr_r 0x02400000; '
        'setenv fdt_addr_r 0x02600000; '
        'setenv pxefile_addr_r 0x03000000; '
        'for indigo_mmc in 1 0; do '
        'if mmc dev ${indigo_mmc}; then '
        'echo Loading extlinux from mmc ${indigo_mmc}:1; '
        'sysboot mmc ${indigo_mmc}:1 any ${pxefile_addr_r} '
        '/boot/extlinux/extlinux.conf; fi; done; '
        'echo No bootable Indigo storage configuration; fastboot usb 0'
    )
    extra = extra.replace('CONFIG_BOOTCOMMAND="fastboot usb 0"',
                          f'CONFIG_BOOTCOMMAND="{boot_command}"')
    extra += '''
CONFIG_CMD_PXE=y
# CONFIG_MMC_WRITE is not set
# CONFIG_MMC_HW_PARTITIONING is not set
'''
    config_name = 'thinkpad_extlinux_defconfig'
    output = ROOT / 'build/uboot-nura-extlinux'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'storage-boot-plan.json').write_text(json.dumps({
        'source_revision': EXPECTED, 'config_name': config_name,
        'boot_command': boot_command, 'ram_fallback': False,
        'storage_write_commands_enabled': False,
        'boot_order': ['SD mmc1:1', 'internal eMMC mmc0:1'],
        'configuration_path': '/boot/extlinux/extlinux.conf',
        'boot_files_embedded_in_uboot': False,
        'boot_file_hashes_embedded_in_uboot': False,
        'memory_layout': {'kernel': '0x01000000', 'initramfs': '0x02400000',
                          'dtb': '0x02600000', 'configuration': '0x03000000'},
    }, indent=2) + '\n')
if args.nura_storage_test or args.nura_storage:
    # Keep the released RAM payload and its locked inputs unchanged. These
    # profiles only read storage; the test alone has copies for RAM recovery.
    lock = json.loads((ROOT / 'port/image-inputs.lock.json').read_text())
    manifest = json.loads((ROOT / 'build/nura-sd-test/payload-manifest.json').read_text())
    boot_paths = {'kernel': '/boot/vmlinuz-indigo',
                  'initramfs': '/boot/initramfs-indigo',
                  'dtb': '/boot/tegra20-lenovo-indigo.dtb'}
    components = [c for c in manifest['components'] if c['name'] in boot_paths]
    if [c['name'] for c in components] != ['kernel', 'initramfs', 'dtb']:
        raise SystemExit('Unexpected released RAM component layout')
    for component in components:
        relative = component['path']
        data = (ROOT / relative).read_bytes()
        if (len(data) != component['size'] or
                hashlib.sha256(data).hexdigest() != component['sha256'] or
                component['sha256'] != lock['files'][relative]):
            raise SystemExit(f'Released component differs from lock: {relative}')
    prefix = ROOT / 'backups/MP0GKR7-20261005T160450Z/boot-prefix.img'
    if prefix.stat().st_size != 10 * 1024 * 1024:
        raise SystemExit('Unexpected saved eMMC prefix size')
    prefix_hash = hashlib.sha256(prefix.read_bytes()[:1024 * 1024]).hexdigest()
    base_args = 'console=tty0 console=ttyS0,115200 loglevel=7 panic=0 rdinit=/init'
    backups = ['0x05000000', '0x06000000', '0x06200000']
    commands = []
    if args.nura_storage_test:
        commands += [f'cp.b {c["address"]} {address} 0x{c["size"]:x}'
                     for c, address in zip(components, backups)]
    commands += [
        'setenv indigo_emmc fail',
        'if mmc dev 0 && mmc read 0x03000000 0 0x800 && '
        f'hash -v sha256 0x03000000 0x100000 {prefix_hash}; '
        'then setenv indigo_emmc pass; fi',
        'setenv indigo_stage sd-select',
        'if mmc dev 1',
    ]
    for component in components:
        name = component['name']
        commands += [
            f'then setenv indigo_stage {name}; '
            f'if ext4load mmc 1:1 {component["address"]} {boot_paths[name]} '
            f'0x{component["size"]:x} && '
            f'test ${{filesize}} = {component["size"]:x} && '
            f'hash -v sha256 {component["address"]} 0x{component["size"]:x} '
            f'{component["sha256"]}',
        ]
    commands += [
        'then setenv indigo_stage bootz',
        f'setenv bootargs {base_args} indigo_boot=sd-sha256 '
        'indigo_emmc=${indigo_emmc}',
        'echo Starting SHA256-verified Linux from SD',
        f'bootz {components[0]["address"]} '
        f'{components[1]["address"]}:0x{components[1]["size"]:x} '
        f'{components[2]["address"]}',
        'fi; fi; fi; fi',
    ]
    if args.nura_storage_test:
        commands += [f'cp.b {address} {c["address"]} 0x{c["size"]:x}'
                     for c, address in zip(components, backups)]
        commands += [
            f'setenv bootargs {base_args} indigo_boot=ram-fallback '
            'indigo_stage=${indigo_stage} indigo_emmc=${indigo_emmc}',
            'echo SD boot failed - using APX RAM rescue',
            f'bootz {components[0]["address"]} '
            f'{components[1]["address"]}:0x{components[1]["size"]:x} '
            f'{components[2]["address"]}',
        ]
    else:
        commands += ['echo SD boot failed at ${indigo_stage}', 'fastboot usb 0']
    boot_command = '; '.join(commands)
    extra = extra.replace('CONFIG_BOOTCOMMAND="fastboot usb 0"',
                          f'CONFIG_BOOTCOMMAND="{boot_command}"')
    extra += '''
CONFIG_CMD_HASH=y
CONFIG_HASH_VERIFY=y
CONFIG_SHA256=y
# CONFIG_MMC_WRITE is not set
# CONFIG_MMC_HW_PARTITIONING is not set
'''
    config_name = ('thinkpad_storage_test_defconfig' if args.nura_storage_test
                   else 'thinkpad_storage_defconfig')
    output = ROOT / ('build/uboot-nura-storage-test' if args.nura_storage_test
                     else 'build/uboot-nura-storage')
    output.mkdir(parents=True, exist_ok=True)
    (output / 'storage-boot-plan.json').write_text(json.dumps({
        'source_revision': EXPECTED, 'config_name': config_name,
        'boot_command': boot_command, 'ram_fallback': args.nura_storage_test,
        'storage_write_commands_enabled': False,
        'emmc_read': {'uboot_mmc': 0, 'start_sector': 0, 'sectors': 2048,
                      'expected_sha256': prefix_hash},
        'sd_boot': {'uboot_mmc': '1:1', 'components': [
            dict(c, storage_path=boot_paths[c['name']]) for c in components]},
    }, indent=2) + '\n')
(SOURCE / f'configs/{config_name}').write_text(original + '\n' + extra)

original_dts = subprocess.check_output(
    ['git', '-C', str(SOURCE), 'show', 'HEAD:arch/arm/dts/tegra20-ventana.dts'], text=True)
old = '\tusb@c5000000 {\n\t\tstatus = "okay";\n\t};'
new = '\tusb@c5000000 {\n\t\tstatus = "okay";\n\t\tdr_mode = "peripheral";\n\t};'
if original_dts.count(old) != 1:
    raise SystemExit('Unexpected USB controller device-tree layout')
(SOURCE / 'arch/arm/dts/tegra20-ventana.dts').write_text(original_dts.replace(old, new))
print(f'Prepared {config_name}: transient environment, flash/format disabled.')
