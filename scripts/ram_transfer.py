#!/usr/bin/env python3
"""Transfer files over the diagnostic shell, with end-to-end SHA256 checks.

Uploads are restricted to RAM-backed /tmp or /run. Downloads only read files.
"""
import argparse
import base64
import hashlib
import os
import re
import select
import shlex
import time
import tty
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('direction', choices=['upload', 'download'])
parser.add_argument('local', type=Path)
parser.add_argument('remote')
parser.add_argument('--device', default='/dev/ttyACM0')
parser.add_argument('--timeout', type=float, default=45)
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
remote = shlex.quote(args.remote)
if args.direction == 'upload':
    parts = Path(args.remote).parts
    if len(parts) < 3 or parts[1] not in ('tmp', 'run') or '..' in parts:
        raise SystemExit('Uploads must target /tmp or /run in the diagnostic RAM environment')
    source = args.local.read_bytes()
    payload = (
        f"\n/bin/busybox base64 -d > {remote} <<'THINKPAD_PAYLOAD_END'\n".encode()
        + base64.encodebytes(source)
        + f'THINKPAD_PAYLOAD_END\n/bin/busybox sha256sum {remote}; echo THINKPAD_TRANSFER_DONE\n'.encode()
    )
else:
    payload = (f'\necho THINKPAD_DATA_BEGIN; /bin/busybox base64 {remote}; '
               f'echo THINKPAD_DATA_END; /bin/busybox sha256sum {remote}; '
               'echo THINKPAD_TRANSFER_DONE\n').encode()
fd = os.open(node, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
tty.setraw(fd)
data = bytearray()
pending = memoryview(payload)
deadline = time.monotonic() + args.timeout
try:
    while time.monotonic() < deadline:
        readable, writable, _ = select.select([fd], [fd] if pending else [], [], 0.1)
        if readable:
            try:
                chunk = os.read(fd, 65536)
                if chunk:
                    data.extend(chunk)
            except BlockingIOError:
                pass
        if writable:
            try:
                count = os.write(fd, pending[:2048])
                pending = pending[count:]
            except BlockingIOError:
                pass
        if not pending and b'\r\nTHINKPAD_TRANSFER_DONE\r\n' in data:
            break
finally:
    os.close(fd)
transcript = bytes(data).replace(b'\r\n', b'\n')
hashes = re.findall(rb'(?:^|\n)([0-9a-f]{64})  ', transcript)
if not hashes:
    print(transcript[-2000:].decode(errors='replace'))
    raise SystemExit('No device SHA256 received; transfer incomplete')
if args.direction == 'download':
    try:
        encoded = transcript.split(b'\nTHINKPAD_DATA_BEGIN\n', 1)[1].split(b'\nTHINKPAD_DATA_END\n', 1)[0]
        source = base64.b64decode(b''.join(encoded.split()), validate=True)
    except (IndexError, ValueError) as error:
        raise SystemExit(f'Invalid framed download: {error}')
actual = hashlib.sha256(source).hexdigest()
if actual != hashes[-1].decode():
    raise SystemExit(f'Transfer SHA256 mismatch: local {actual}, device {hashes[-1].decode()}')
if args.direction == 'download':
    args.local.parent.mkdir(parents=True, exist_ok=True)
    args.local.write_bytes(source)
print(f'{args.direction}: {len(source)} bytes; SHA256 {actual}; {args.local} <-> {args.remote}')
