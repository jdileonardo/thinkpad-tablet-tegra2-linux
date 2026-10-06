#!/usr/bin/env python3
"""Read-only observation of N-Trig replies, touch events and Xorg continuity."""
import argparse
import json
import os
from pathlib import Path
import select
import struct
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--seconds', type=int, default=120)
parser.add_argument('--output', required=True)
args = parser.parse_args()
if not 10 <= args.seconds <= 3600:
    parser.error('Duration must be 10..3600 seconds')
stats = Path('/sys/bus/spi/devices/spi0.0/stats')
event = next(path for path in Path('/sys/class/input').glob('event*')
             if (path / 'device/name').read_text().strip() == 'N-Trig Indigo Touchscreen')
fd = os.open('/dev/input/' + event.name, os.O_RDONLY | os.O_NONBLOCK)
format_ = struct.Struct('llHHi')
report = {'event_device': event.name, 'samples': [], 'event_count': 0,
          'first_events': [], 'duration_requested': args.seconds}
start = time.monotonic()
next_sample = start
try:
    while time.monotonic() - start < args.seconds:
        now = time.monotonic()
        if now >= next_sample:
            fields = dict(word.split('=', 1) for word in stats.read_text().split()
                          if '=' in word)
            counters = {key: int(fields[key]) for key in
                        ('transfers', 'packets', 'invalid', 'touch', 'pen', 'errors',
                         'watchdog_misses', 'resets')}
            xorg = {}
            for directory in Path('/proc').glob('[0-9]*'):
                try:
                    if (directory / 'comm').read_text().strip() == 'Xorg':
                        xorg[directory.name] = int((directory / 'stat').read_text()
                                                  .rsplit(')', 1)[1].split()[19])
                except (OSError, ValueError):
                    pass
            report['samples'].append({'seconds': now - start, 'counters': counters,
                                      'xorg_start_ticks': xorg})
            next_sample = now + 5
        readable, _, _ = select.select([fd], [], [], 0.25)
        if readable:
            payload = os.read(fd, format_.size * 64)
            for offset in range(0, len(payload), format_.size):
                sec, usec, type_, code, value = format_.unpack_from(payload, offset)
                report['event_count'] += 1
                if len(report['first_events']) < 64:
                    report['first_events'].append({'type': type_, 'code': code, 'value': value})
    report['duration_seconds'] = time.monotonic() - start
finally:
    os.close(fd)
    Path(args.output).write_text(json.dumps(report, indent=2) + '\n')
