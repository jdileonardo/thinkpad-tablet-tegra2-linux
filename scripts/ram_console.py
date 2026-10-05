#!/usr/bin/env python3
"""Collect the ThinkPad diagnostic USB shell; default commands are read-only."""
import argparse
import os
import re
import select
import time
import tty
from datetime import datetime, timezone
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--device', default='/dev/ttyACM0')
parser.add_argument('--seconds', type=float, default=12)
parser.add_argument('--command', action='append')
args = parser.parse_args()
node = Path(args.device)
usb_parent = None
for parent in (Path('/sys/class/tty') / node.name / 'device').resolve().parents:
    if (parent / 'idVendor').exists():
        usb_parent = parent
        break
if usb_parent is None or (usb_parent / 'idVendor').read_text().strip() != '17ef' \
        or (usb_parent / 'product').read_text().strip() != 'Diagnostic RAM console':
    raise SystemExit('Selected tty is not the ThinkPad diagnostic RAM console')
commands = args.command or [
    'uname -a', 'cat /proc/cmdline', 'cat /proc/mounts', 'head /proc/meminfo',
    'ls /sys/class/udc', 'cat /proc/partitions', 'ls /sys/class/drm',
    'cat /proc/bus/input/devices',
]
fd = os.open(node, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
tty.setraw(fd)
data = bytearray()
command_payload = ('\n'.join(commands) + '\n').encode()
pending = b'\n'
commands_started = False
deadline = time.monotonic() + args.seconds
try:
    while time.monotonic() < deadline:
        readable, writable, _ = select.select([fd], [fd] if pending else [], [], 0.2)
        if readable:
            try:
                chunk = os.read(fd, 65536)
                if chunk:
                    data.extend(chunk)
                    if not commands_started and re.search(rb'(?:^|[\r\n])[^\r\n]*# ', data):
                        pending = command_payload
                        commands_started = True
            except BlockingIOError:
                pass
        if writable:
            try:
                count = os.write(fd, pending)
                pending = pending[count:]
            except BlockingIOError:
                pass
finally:
    os.close(fd)
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
output = Path(__file__).resolve().parents[1] / f'diagnostics/linux-console-{stamp}.txt'
output.write_bytes(data)
print(data.decode(errors='replace'))
print(f'Captured {len(data)} bytes in {output}')
if not commands_started:
    raise SystemExit('Diagnostic shell prompt was not received')
if pending:
    raise SystemExit('Some commands could not be sent')
