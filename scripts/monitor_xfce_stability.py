#!/usr/bin/env python3
"""Bounded, read-only Indigo XFCE observation; reports go under /tmp or /run.

Samples include this observer's small overhead. No desktop restart, renderer
override, cache dropping, benchmark load or raw-device writes are performed.
"""
import argparse
import ipaddress
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def read(path):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def kernel_log():
    result = subprocess.run(['dmesg'], capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise RuntimeError('Cannot read kernel log')
    return result.stdout.splitlines()


def processes():
    result = []
    for directory in Path('/proc').glob('[0-9]*'):
        try:
            name = (directory / 'comm').read_text().strip()
            if not (name.startswith(('xfce', 'xfwm', 'xfdesktop', 'lightdm')) or
                    name in ('Xorg', 'python3', 'NetworkManager', 'dbus-daemon')):
                continue
            status = dict(line.split(':', 1) for line in
                          (directory / 'status').read_text().splitlines())
            stat = (directory / 'stat').read_text().rsplit(')', 1)[1].split()
            result.append({'pid': int(directory.name), 'name': name,
                           'start_ticks': int(stat[19]),
                           'cpu_ticks': int(stat[11]) + int(stat[12]),
                           'rss_kib': int(status.get('VmRSS', '0 kB').split()[0])})
        except (OSError, ValueError, IndexError):
            # Short-lived processes can disappear between procfs reads.
            continue
    return sorted(result, key=lambda process: process['pid'])


def snapshot(peer):
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        if key in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree',
                   'CmaTotal', 'CmaFree', 'Slab', 'PageTables'):
            memory[key] = int(value.split()[0])
    sample = {'monotonic': time.monotonic(), 'memory_kib': memory,
              'cpu_ticks': list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:9])),
              'processes': processes(), 'temperatures_c': {},
              'pressure': {name: read('/proc/pressure/' + name)
                           for name in ('cpu', 'memory', 'io')},
              'wifi': {'operstate': read('/sys/class/net/wlan0/operstate'),
                       'statistics': {}},
              'zram_mm_stat': read('/sys/block/zram0/mm_stat')}
    for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
        try:
            sample['temperatures_c'][(zone / 'type').read_text().strip()] = float((zone / 'temp').read_text()) / 1000
        except (OSError, ValueError):
            pass
    for name in ('rx_bytes', 'tx_bytes', 'rx_errors', 'tx_errors', 'rx_dropped', 'tx_dropped'):
        value = read('/sys/class/net/wlan0/statistics/' + name)
        sample['wifi']['statistics'][name] = int(value) if value is not None else None
    if peer:
        ping = subprocess.run(['ping', '-I', 'wlan0', '-c', '1', '-W', '2', peer],
                              capture_output=True, text=True, timeout=4)
        latency = re.search(r'time[=<]([0-9.]+) ms', ping.stdout)
        sample['wifi']['ping'] = {'peer': peer, 'exit_code': ping.returncode,
                                  'latency_ms': float(latency[1]) if latency else None}
    return sample


def cpu_busy(first, last):
    delta = [b - a for a, b in zip(first, last)]
    return 100 * (sum(delta) - delta[3] - delta[4]) / max(1, sum(delta))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=600)
    parser.add_argument('--interval', type=int, default=10)
    parser.add_argument('--peer', help='Optional local IPv4 peer to ping over wlan0')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 10 <= args.seconds <= 3600 or not 2 <= args.interval <= 60:
        parser.error('Use 10..3600 seconds and a 2..60 second interval')
    if args.peer:
        peer = ipaddress.IPv4Address(args.peer)
        if not peer.is_private or peer.is_loopback or peer.is_unspecified:
            parser.error('Peer must be a local private IPv4 address')
    output = args.output.resolve()
    if not any(output.is_relative_to(Path(base)) for base in ('/tmp', '/run')):
        parser.error('Output must be under /tmp or /run')
    root = next(line.split()[0] for line in Path('/proc/mounts').read_text().splitlines()
                if line.split()[1] == '/')
    block = (Path('/sys/class/block') / Path(root).name).resolve()
    if os.geteuid() != 0 or 'c8000400.mmc' not in str(block):
        raise RuntimeError('Run as root on the Indigo external-SD system')
    journal = output.with_suffix('.jsonl')
    if output.exists() or journal.exists():
        raise RuntimeError('Use a fresh output path')
    before = kernel_log()
    started = time.monotonic()
    samples = []
    with journal.open('x') as handle:
        while True:
            sample = snapshot(args.peer)
            samples.append(sample)
            handle.write(json.dumps(sample) + '\n')
            handle.flush()
            if len(samples) == 1 or (len(samples) - 1) * args.interval % 60 == 0:
                print(f"elapsed={sample['monotonic'] - started:.0f}s "
                      f"available={sample['memory_kib']['MemAvailable'] / 1024:.1f}MiB "
                      f"CMA_free={sample['memory_kib']['CmaFree'] / 1024:.1f}MiB", flush=True)
            remaining = args.seconds - (time.monotonic() - started)
            if remaining <= 0:
                break
            time.sleep(min(args.interval, remaining))
    after = kernel_log()
    # Only claim exact new lines if the initial log remains a prefix.
    log_prefix_preserved = after[:len(before)] == before
    new_lines = after[len(before):] if log_prefix_preserved else None
    summary = {
        'observed_seconds': samples[-1]['monotonic'] - samples[0]['monotonic'],
        'sample_count': len(samples),
        'cpu_busy_percent_of_both_cores': cpu_busy(samples[0]['cpu_ticks'], samples[-1]['cpu_ticks']),
        'available_mib_range': [min(s['memory_kib']['MemAvailable'] for s in samples) / 1024,
                                max(s['memory_kib']['MemAvailable'] for s in samples) / 1024],
        'cma_free_mib_range': [min(s['memory_kib']['CmaFree'] for s in samples) / 1024,
                               max(s['memory_kib']['CmaFree'] for s in samples) / 1024],
        'max_swap_used_mib': max(s['memory_kib']['SwapTotal'] - s['memory_kib']['SwapFree'] for s in samples) / 1024,
        'max_temperature_c': max((v for s in samples for v in s['temperatures_c'].values()), default=None),
        'xorg_identities': sorted({(p['pid'], p['start_ticks']) for s in samples
                                  for p in s['processes'] if p['name'] == 'Xorg'}),
        'all_samples_have_xorg_and_xfce_session': all(
            any(p['name'] == 'Xorg' for p in s['processes']) and
            any(p['name'] == 'xfce4-session' for p in s['processes']) for s in samples),
        'wifi_ping_checks': sum('ping' in s['wifi'] for s in samples),
        'wifi_ping_failures': sum(s['wifi'].get('ping', {}).get('exit_code', 0) != 0 for s in samples),
        'kernel_log_prefix_preserved': log_prefix_preserved,
        'new_kernel_messages': new_lines,
        'kernel_error_candidates': [line for line in (new_lines if new_lines is not None else after)
                                    if re.search(r'failed to allocate|bad page|GPU.*hang|Out of memory|Oops|panic', line, re.I)],
    }
    report = {'created_utc': datetime.now(timezone.utc).isoformat(),
              'kernel': os.uname().release, 'root_device': root,
              'requested_seconds': args.seconds, 'interval_seconds': args.interval,
              'observer_pid': os.getpid(), 'summary': summary,
              'kernel_log_before': before, 'kernel_log_after': after, 'samples': samples}
    with output.open('x') as handle:
        json.dump(report, handle, indent=2)
        handle.write('\n')
    print(json.dumps(summary), flush=True)
    print(f'Report: {output}', flush=True)


if __name__ == '__main__':
    main()
