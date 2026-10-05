#!/usr/bin/env python3
"""Build a reproducible diagnostic initramfs; it never mounts tablet storage."""
import gzip
import stat
from pathlib import Path

root = Path(__file__).resolve().parents[1]
out = root / 'build/ram-test'
out.mkdir(parents=True, exist_ok=True)
entries = []


def add(name, mode, data=b'', rdev=(0, 0)):
    entries.append((name, mode, data, rdev))


for name in ['bin', 'dev', 'etc', 'proc', 'sys', 'run', 'tmp']:
    add(name, stat.S_IFDIR | 0o755)
add('dev/console', stat.S_IFCHR | 0o600, rdev=(5, 1))
add('dev/null', stat.S_IFCHR | 0o666, rdev=(1, 3))
add('bin/busybox', stat.S_IFREG | 0o755, (root / 'build/busybox/busybox').read_bytes())
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
