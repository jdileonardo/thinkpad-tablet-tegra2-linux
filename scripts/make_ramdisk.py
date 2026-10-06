#!/usr/bin/env python3
"""Build diagnostic, SD, or explicitly selected internal-root bootstraps."""
import gzip
import stat
import argparse
import uuid
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--profile', choices=['historical', 'nura', 'nura-sd', 'nura-internal'], default='historical')
parser.add_argument('--root-uuid', help='Required filesystem UUID for either storage profile')
args = parser.parse_args()
storage_profile = args.profile in ('nura-sd', 'nura-internal')
if storage_profile:
    if not args.root_uuid:
        parser.error('Storage profiles require --root-uuid')
    args.root_uuid = str(uuid.UUID(args.root_uuid))
out = root / {'historical': 'build/ram-test', 'nura': 'build/nura-ram-test',
              'nura-sd': 'build/nura-sd-test',
              'nura-internal': 'build/nura-internal-test'}[args.profile]
out.mkdir(parents=True, exist_ok=True)
entries = []


def add(name, mode, data=b'', rdev=(0, 0)):
    entries.append((name, mode, data, rdev))


for name in ['bin', 'dev', 'etc', 'proc', 'sys', 'run', 'tmp']:
    add(name, stat.S_IFDIR | 0o755)
add('dev/console', stat.S_IFCHR | 0o600, rdev=(5, 1))
add('dev/null', stat.S_IFCHR | 0o666, rdev=(1, 3))
add('bin/busybox', stat.S_IFREG | 0o755, (root / 'build/busybox/busybox').read_bytes())
if args.profile != 'historical':
    for directory in ['lib', 'lib/firmware', 'lib/firmware/brcm']:
        add(directory, stat.S_IFDIR | 0o755)
    for filename in ['brcmfmac4329-sdio.bin', 'brcmfmac4329-sdio.txt']:
        firmware_dir = 'build/linux-firmware' if filename.endswith('.bin') else 'build/stock/firmware'
        add('lib/firmware/brcm/' + filename, stat.S_IFREG | 0o644,
            (root / firmware_dir / filename).read_bytes())
    add('lib/firmware/LICENCE.broadcom_bcm43xx', stat.S_IFREG | 0o644,
        (root / 'build/linux-firmware/LICENCE.broadcom_bcm43xx').read_bytes())
    for filename in (['regulatory.db', 'regulatory.db.p7s'] if storage_profile else []):
        add('lib/firmware/' + filename, stat.S_IFREG | 0o644,
            (root / 'build/pmbootstrap/chroot_rootfs_nvidia-tegra-armv7/lib/firmware' / filename).read_bytes())
    add('bin/reboot-into-apx', stat.S_IFREG | 0o755,
        (root / 'build/ram-test/reboot-into-apx').read_bytes())
for name in ['sh', 'mount', 'mkdir', 'cat', 'sleep', 'setsid', 'cttyhack', 'uname',
             'dmesg', 'ls', 'find', 'ip', 'ifconfig', 'reboot', 'poweroff', 'echo',
             'grep', 'head', 'tail', 'hexdump', 'sync', 'stty', 'env']:
    add('bin/' + name, stat.S_IFLNK | 0o777, b'busybox')
init = '''#!/bin/sh
export PATH=/bin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mount -t tmpfs tmpfs /run
mount -t tmpfs tmpfs /tmp
mkdir -p /sys/kernel/config
mount -t configfs configfs /sys/kernel/config
echo 'ThinkPad diagnostic RAM boot: internal storage is not mounted.' >/dev/console
g=/sys/kernel/config/usb_gadget/thinkpad
mkdir -p "$g"
echo 0x17ef >"$g/idVendor"
echo 0x741c >"$g/idProduct"
mkdir -p "$g/strings/0x409"
echo thinkpad-ram-test >"$g/strings/0x409/serialnumber"
echo 'Lenovo ThinkPad port' >"$g/strings/0x409/manufacturer"
echo 'Diagnostic RAM console' >"$g/strings/0x409/product"
mkdir -p "$g/configs/c.1/strings/0x409"
echo 'USB serial console' >"$g/configs/c.1/strings/0x409/configuration"
echo 250 >"$g/configs/c.1/MaxPower"
mkdir -p "$g/functions/acm.usb0"
/bin/busybox ln -s "$g/functions/acm.usb0" "$g/configs/c.1/acm.usb0"
while :; do
    for u in /sys/class/udc/*; do
        [ -e "$u" ] || continue
        echo "${u##*/}" >"$g/UDC"
        break 2
    done
    echo 'Waiting for Tegra USB device controller' >/dev/console
    sleep 2
done
while :; do
    echo 'ThinkPad RAM test console. No internal filesystems mounted.' >/dev/ttyGS0
    uname -a >/dev/ttyGS0
    dmesg >/dev/ttyGS0
    # cttyhack would select the physical UART from console/active.
    # Explicitly make USB serial stdin the shell's controlling terminal.
    setsid -c sh -i </dev/ttyGS0 >/dev/ttyGS0 2>&1
    sleep 1
done
'''
if storage_profile:
    switch = '''# Only the external SD controller is eligible for the OS root.
mkdir -p /newroot
rootdev=
tries=0
while [ "$tries" -lt 60 ]; do
    for block in /sys/class/block/mmcblk*p*; do
        [ -e "$block" ] || continue
        case "$(/bin/busybox readlink -f "$block")" in
            *c8000400.mmc*) ;;
            *) continue ;;
        esac
        dev=/dev/${block##*/}
        found=$(/bin/busybox blkid "$dev" | /bin/busybox sed -n 's/.*UUID="\\([^"]*\\)".*/\\1/p')
        [ "$found" = 'ROOT_UUID' ] && rootdev=$dev && break
    done
    [ -n "$rootdev" ] && break
    tries=$((tries + 1))
    sleep 1
done
if [ -n "$rootdev" ] && mount -t ext4 -o rw "$rootdev" /newroot; then
    if [ -x /newroot/sbin/init ]; then
        echo "Starting Nura from external SD: $rootdev" >/dev/console
        for fs in proc sys dev run; do
            mkdir -p /newroot/$fs
            mount --move /$fs /newroot/$fs || exit 1
        done
        exec /bin/busybox switch_root /newroot /sbin/init
    fi
    /bin/busybox umount /newroot
fi
echo 'SD root unavailable; staying in RAM rescue console.' >/dev/console
'''.replace('ROOT_UUID', args.root_uuid)
    if args.profile == 'nura-internal':
        switch = switch.replace('external SD controller', 'internal eMMC controller')
        switch = switch.replace('c8000400.mmc', 'c8000600.mmc')
        switch = switch.replace('external SD', 'internal eMMC')
        switch = switch.replace('SD root unavailable', 'Internal root unavailable')
        switch = switch.replace('s/.*UUID=', 's/.* UUID=')
        init = init.replace('internal storage is not mounted.',
                            'internal root requires the configured eMMC controller and UUID.')
    init = init.replace('while :; do\n    echo \'ThinkPad RAM test console.',
                        switch + 'while :; do\n    echo \'ThinkPad RAM test console.')
add('init', stat.S_IFREG | 0o755, init.encode())
add('etc/issue', stat.S_IFREG | 0o644, b'ThinkPad RAM diagnostic environment\n')
add('TRAILER!!!', 0)
archive = bytearray()
for ino, (name, mode, data, rdev) in enumerate(entries, 1):
    path = name.encode() + b'\0'
    fields = [ino, mode, 0, 0, 1, 0, len(data), 0, 0, *rdev, len(path), 0]
    archive.extend(b'070701' + ''.join(f'{x:08x}' for x in fields).encode())
    archive.extend(path)
    archive.extend(b'\0' * (-len(archive) % 4))
    archive.extend(data)
    archive.extend(b'\0' * (-len(archive) % 4))
(out / 'initramfs.cpio.gz').write_bytes(gzip.compress(bytes(archive), mtime=0))
(out / 'init').write_text(init)
print(f'Wrote {out / "initramfs.cpio.gz"}')
