#!/usr/bin/env python3
"""Bounded private trace of ARM DDX pixmap creation and kernel GEM allocation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import time
import uuid

TRACE = Path('/sys/kernel/tracing')
MODULE = Path('/opt/indigo-xorg/xfce/lib/xorg/modules/drivers/opentegra_drv.so')


def control(file, line):
    fd = os.open(TRACE / file, os.O_WRONLY | os.O_APPEND)
    try:
        os.write(fd, (line + '\n').encode())
    finally:
        os.close(fd)


def cleanup(name):
    if not re.fullmatch(r'indigo_big_[0-9a-f]{12}', name):
        raise ValueError('Invalid owned trace name')
    instance = TRACE / 'instances' / name
    if instance.exists():
        (instance / 'tracing_on').write_text('0\n')
        (instance / 'events/enable').write_text('0\n')
        instance.rmdir()
    for file, events in [('uprobe_events', ['pixmap']),
                         ('kprobe_events', ['bo_create', 'bo_return', 'bo_free'])]:
        for event in events:
            if (TRACE / 'events' / name / event).exists():
                control(file, f'-:{name}/{event}')


def entry_offset(data):
    if data[:6] != b'\x7fELF\x01\x01':
        raise RuntimeError('Expected little endian ARM32 ELF')
    header = struct.unpack_from('<HHIIIIIHHHHHH', data, 16)
    sections = [struct.unpack_from('<IIIIIIIIII', data, header[5] + i * header[10])
                for i in range(header[11])]
    for section in sections:
        if section[1] != 2:
            continue
        table = sections[section[6]]
        strings = data[table[4]:table[4] + table[5]]
        for offset in range(section[4], section[4] + section[5], 16):
            name, value, size, info, other, index = struct.unpack_from('<IIIBBH', data, offset)
            if strings[name:].split(b'\0')[0] == b'TegraEXACreatePixmap2':
                text = sections[index]
                if value % 4:
                    raise RuntimeError('ARM kernel uprobes do not support Thumb')
                return value - text[3] + text[4]
    raise RuntimeError('DDX pixmap function symbol not found')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cleanup')
    parser.add_argument('--seconds', type=int, default=120)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--module', type=Path, default=MODULE)
    args = parser.parse_args()
    if args.cleanup:
        cleanup(args.cleanup)
        return
    if os.geteuid() or not args.output or not 10 <= args.seconds <= 300:
        parser.error('Run as root with output and 10..300 seconds')
    root = next(l.split()[0] for l in Path('/proc/mounts').read_text().splitlines()
                if l.split()[1] == '/')
    if 'c8000400.mmc' not in str((Path('/sys/class/block') / Path(root).name).resolve()):
        raise RuntimeError('Expected external SD root')
    output = args.output.resolve()
    if not output.is_relative_to(Path('/tmp')) or output.exists():
        parser.error('Use a fresh output directory under /tmp')
    output.mkdir()
    if args.module not in (MODULE, Path('/opt/indigo-xorg/dri3/lib/xorg/modules/drivers/opentegra_drv.so')):
        parser.error('Expected a known private Indigo Xorg module path')
    data = args.module.read_bytes()
    offset = entry_offset(data)
    name = 'indigo_big_' + uuid.uuid4().hex[:12]
    instance = TRACE / 'instances' / name
    report = {'module_sha256': hashlib.sha256(data).hexdigest(), 'entry_offset': hex(offset),
              'trace_name': name, 'kernel_before': subprocess.check_output(['dmesg'], text=True)}
    try:
        instance.mkdir()
        (instance / 'tracing_on').write_text('0\n')
        (instance / 'buffer_size_kb').write_text('512\n')
        control('uprobe_events', f'p:{name}/pixmap {args.module}:0x{offset:x} '
                'width=%r1:u32 height=%r2:u32 depth=%r3:u32 bpp=+4(%sp):u32 usage=+0(%sp):u32')
        control('kprobe_events', f'p:{name}/bo_create tegra_bo_create size=%r1:u32 flags=%r2:x32')
        control('kprobe_events', f'r:{name}/bo_return tegra_bo_create result=$retval:x32')
        control('kprobe_events', f'p:{name}/bo_free tegra_bo_free bo=%r1:x32')
        (instance / 'events' / name / 'enable').write_text('1\n')
        with (output / 'watchdog.log').open('w') as log:
            subprocess.Popen(['sh', '-c', 'sleep "$1"; exec python3 "$2" --cleanup "$3"',
                              'oversize-cleanup', str(args.seconds + 30), str(Path(__file__).resolve()), name],
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        (instance / 'tracing_on').write_text('1\n')
        print('OVERSIZE_TRACE_READY', flush=True)
        time.sleep(args.seconds)
        (instance / 'tracing_on').write_text('0\n')
        (output / 'trace.txt').write_text((instance / 'trace').read_text())
        report['stats'] = {p.parent.name: p.read_text() for p in (instance / 'per_cpu').glob('cpu*/stats')}
        report['kernel_after'] = subprocess.check_output(['dmesg'], text=True)
    finally:
        cleanup(name)
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Oversize trace saved and all probes removed', flush=True)


if __name__ == '__main__':
    main()
