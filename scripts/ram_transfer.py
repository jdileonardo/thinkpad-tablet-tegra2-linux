#!/usr/bin/env python3
"""Transfer files over the diagnostic shell, with end-to-end SHA256 checks.

Uploads are restricted to /tmp or /run on the diagnostic OS. Downloads only read files.
"""
import argparse
import base64
import fcntl
import hashlib
import os
import re
import select
import shlex
import time
import tty
import uuid
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('direction', choices=['upload', 'download'])
parser.add_argument('local', type=Path)
parser.add_argument('remote')
parser.add_argument('--device', default='/dev/ttyACM0')
parser.add_argument('--timeout', type=float, default=45)
parser.add_argument('--private', action='store_true',
                    help='Create uploads with mode 0600 and suppress transcript/hash output')
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
# Unique frames ignore replies still buffered from a previous transfer. Use
# printf with literal escapes so a wrapped terminal echo cannot look like an
# actual marker line and end the observation before the command executes.
transfer_id = uuid.uuid4().hex
begin_marker = 'THINKPAD_DATA_BEGIN_' + transfer_id
end_marker = 'THINKPAD_DATA_END_' + transfer_id
done_marker = 'THINKPAD_TRANSFER_DONE_' + transfer_id
payload_marker = 'THINKPAD_PAYLOAD_END_' + transfer_id
if args.direction == 'upload':
    parts = Path(args.remote).parts
    if len(parts) < 3 or parts[1] not in ('tmp', 'run') or '..' in parts:
        raise SystemExit('Uploads must target /tmp or /run on the diagnostic OS')
    source = args.local.read_bytes()
    payload = (
        (f'\nthinkpad_transfer_umask=$(umask); umask 077\n' if args.private else '\n').encode()
        + f"/bin/busybox base64 -d > {remote} <<'{payload_marker}'\n".encode()
        + base64.encodebytes(source)
        + f"{payload_marker}\nprintf '\\n'; /bin/busybox sha256sum {remote}; printf '\\n{done_marker}\\n'\n".encode()
        + (b'umask "$thinkpad_transfer_umask"\n' if args.private else b'')
    )
else:
    payload = (f"\nprintf '\\n{begin_marker}\\n'; /bin/busybox base64 {remote}; "
               f"printf '\\n{end_marker}\\n'; printf '\\n'; /bin/busybox sha256sum {remote}; "
               f"printf '\\n{done_marker}\\n'\n").encode()
fd = os.open(node, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    os.close(fd)
    raise SystemExit('Diagnostic console is in use; finish the other console/transfer first')
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
        if not pending and ('\r\n' + done_marker + '\r\n').encode() in data:
            break
finally:
    os.close(fd)
transcript = bytes(data).replace(b'\r\n', b'\n')
hashes = re.findall(rb'(?:^|\n)([0-9a-f]{64})  ', transcript)
if not hashes:
    if not args.private:
        print(transcript[-2000:].decode(errors='replace'))
    raise SystemExit('No device SHA256 received; transfer incomplete')
if args.direction == 'download':
    try:
        encoded = transcript.split(('\n' + begin_marker + '\n').encode(), 1)[1].split(
            ('\n' + end_marker + '\n').encode(), 1)[0]
        source = base64.b64decode(b''.join(encoded.split()), validate=True)
    except (IndexError, ValueError) as error:
        raise SystemExit(f'Invalid framed download: {error}')
actual = hashlib.sha256(source).hexdigest()
if actual != hashes[-1].decode():
    raise SystemExit(f'Transfer SHA256 mismatch: local {actual}, device {hashes[-1].decode()}')
if args.direction == 'download':
    args.local.parent.mkdir(parents=True, exist_ok=True)
    args.local.write_bytes(source)
if args.private:
    print(f'{args.direction}: {len(source)} private bytes; SHA256 verified')
else:
    print(f'{args.direction}: {len(source)} bytes; SHA256 {actual}; {args.local} <-> {args.remote}')
