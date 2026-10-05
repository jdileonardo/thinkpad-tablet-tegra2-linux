#!/usr/bin/env python3
"""Prepare a RAM-only USB fastboot bootstrap in the pinned historical source."""
from pathlib import Path
import subprocess
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--direct-linux', action='store_true')
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
if args.direct_linux:
    ramdisk_size = (ROOT / 'build/ram-test/initramfs.cpio.gz').stat().st_size
    boot_command = (
        'setenv bootargs console=tty0 console=ttyS0,115200 loglevel=7 '
        'panic=0 rdinit=/init; echo Starting ThinkPad diagnostic Linux from RAM; '
        f'bootz 0x01000000 0x02000000:0x{ramdisk_size:x} 0x02200000'
    )
    extra = extra.replace('CONFIG_BOOTCOMMAND="fastboot usb 0"',
                          f'CONFIG_BOOTCOMMAND="{boot_command}"')
(SOURCE / 'configs/thinkpad_ram_defconfig').write_text(original + '\n' + extra)

original_dts = subprocess.check_output(
    ['git', '-C', str(SOURCE), 'show', 'HEAD:arch/arm/dts/tegra20-ventana.dts'], text=True)
old = '\tusb@c5000000 {\n\t\tstatus = "okay";\n\t};'
new = '\tusb@c5000000 {\n\t\tstatus = "okay";\n\t\tdr_mode = "peripheral";\n\t};'
if original_dts.count(old) != 1:
    raise SystemExit('Unexpected USB controller device-tree layout')
(SOURCE / 'arch/arm/dts/tegra20-ventana.dts').write_text(original_dts.replace(old, new))
print('Prepared RAM bootstrap: transient environment, flash/format disabled; '
      + ('direct Linux boot.' if args.direct_linux else 'USB fastboot.'))
