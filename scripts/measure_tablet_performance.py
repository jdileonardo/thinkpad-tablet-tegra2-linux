#!/usr/bin/env python3
"""Bounded on-tablet measurements; writes one temporary 64 MiB external-SD file.

Run on the Indigo Linux console, with mesa-utils, glmark2 and sysbench installed.
No clock/governor changes, cache dropping, raw-disk writes or desktop restarts.
"""
import argparse
import errno
import json
import mmap
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path


def snapshot():
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        if key in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'):
            memory[key] = int(value.split()[0])
    ticks = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
    temperatures = {}
    for zone in Path('/sys/class/thermal').glob('thermal_zone*'):
        try:
            temperatures[(zone / 'type').read_text().strip()] = int((zone / 'temp').read_text()) / 1000
        except (OSError, ValueError):
            pass
    return {'monotonic': time.monotonic(), 'memory_kib': memory,
            'cpu_ticks': ticks, 'temperatures_c': temperatures}


def run(name, command, timeout=35):
    print(f'Starting {name}', flush=True)
    samples = [snapshot()]
    started = time.monotonic()
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        timed_out = False
        while process.poll() is None:
            if time.monotonic() - started > timeout:
                os.killpg(process.pid, signal.SIGKILL)
                timed_out = True
                break
            time.sleep(0.25)
            samples.append(snapshot())
        process.wait()
        samples.append(snapshot())
        output.seek(0)
        transcript = output.read().decode(errors='replace')
    first, last = samples[0]['cpu_ticks'], samples[-1]['cpu_ticks']
    delta = [b - a for a, b in zip(first, last)]
    busy = 100 * (sum(delta) - delta[3] - delta[4]) / max(1, sum(delta))
    result = {'name': name, 'command': command, 'elapsed_seconds': time.monotonic() - started,
              'exit_code': process.returncode, 'timed_out': timed_out,
              'cpu_busy_percent_of_both_cores': busy,
              'min_available_mib': min(s['memory_kib']['MemAvailable'] for s in samples) / 1024,
              'max_swap_used_mib': max(s['memory_kib']['SwapTotal'] - s['memory_kib']['SwapFree'] for s in samples) / 1024,
              'max_temperature_c': max((v for s in samples for v in s['temperatures_c'].values()), default=None),
              'output': transcript, 'samples': samples}
    print(transcript, flush=True)
    print(json.dumps({k: v for k, v in result.items() if k not in ('samples', 'output', 'command')}), flush=True)
    return result


def storage():
    # Verify the root is the external SD controller before creating any test file.
    root = next(line.split()[0] for line in Path('/proc/mounts').read_text().splitlines() if line.split()[1] == '/')
    block = (Path('/sys/class/block') / Path(root).name).resolve()
    if 'c8000400' not in str(block) or os.stat('/var/tmp').st_dev != os.stat('/').st_dev:
        raise RuntimeError(f'Refusing storage test outside external SD root: {root}, {block}')
    size, block_size = 64 * 1024 * 1024, 1024 * 1024
    # Random data avoids measuring zero compression; generation is outside timing.
    data = os.urandom(block_size)
    with tempfile.TemporaryDirectory(prefix='indigo-perf-', dir='/var/tmp') as directory:
        path = Path(directory) / 'io-test.bin'
        started = time.monotonic()
        with path.open('xb', buffering=0) as target:
            for _ in range(size // block_size):
                remaining = memoryview(data)
                while remaining:
                    count = target.write(remaining)
                    if not count:
                        raise RuntimeError('Short storage write')
                    remaining = remaining[count:]
            os.fsync(target.fileno())
        write_seconds = time.monotonic() - started
        result = {'bytes': size, 'root_device': root,
                  'sequential_write_with_fsync_mib_s': size / write_seconds / (1024 * 1024)}
        # O_DIRECT bypasses the OS page cache. The mmap buffer supplies alignment.
        try:
            fd = os.open(path, os.O_RDONLY | os.O_DIRECT)
            try:
                with mmap.mmap(-1, block_size) as buffer:
                    started = time.monotonic()
                    count = 0
                    while count < size:
                        read = os.readv(fd, [buffer])
                        if not read:
                            raise RuntimeError('Short direct storage read')
                        if buffer[:read] != data[:read]:
                            raise RuntimeError('Storage data verification failed')
                        count += read
                    result['direct_read_with_data_verification_mib_s'] = size / (time.monotonic() - started) / (1024 * 1024)
            finally:
                os.close(fd)
        except OSError as error:
            if error.errno not in (errno.EINVAL, errno.ENOTSUP):
                raise
            result['direct_read_unavailable'] = str(error)
        # Includes CPU comparison overhead; not a pure maximum device bandwidth.
        result['temporary_file_removed_after_test'] = True
    print(json.dumps(result), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('/tmp/indigo-performance.json'))
    parser.add_argument('--phase', choices=('system', 'graphics'), required=True)
    parser.add_argument('--driver', choices=('llvmpipe', 'softpipe'),
                        help='Process-local Gallium driver selection for graphics tests')
    parser.add_argument('--private-mesa', action='store_true',
                        help='Run graphics tests through /usr/local/bin/indigo-gpu-run')
    parser.add_argument('--workload', choices=('glmark2', 'simple-triangle'), default='glmark2',
                        help='Graphics workload; simple-triangle checks rendered pixels')
    args = parser.parse_args()
    result = {'phase': args.phase, 'graphics_driver_override': args.driver,
              'private_mesa': args.private_mesa,
              'graphics_workload': args.workload,
              'kernel': os.uname().release, 'baseline': snapshot(), 'tests': []}
    if args.phase == 'system':
        for threads in (1, 2):
            result['tests'].append(run(f'cpu-{threads}-threads',
                ['sysbench', 'cpu', f'--threads={threads}', '--time=10', '--cpu-max-prime=10000', 'run'], timeout=18))
        result['tests'].append(run('memory-sequential-write-16MiB-buffer',
            ['sysbench', 'memory', '--threads=1', '--time=10', '--memory-block-size=16M',
             '--memory-total-size=1G', '--memory-oper=write', '--memory-access-mode=seq', 'run'], timeout=18))
        result['storage'] = storage()
    else:
        for resolution in ('400x300', '800x1280'):
            launcher = '/usr/local/bin/indigo-gpu-run ' if args.private_mesa else ''
            command = (f'DISPLAY=:0 XAUTHORITY=/home/julian/.Xauthority {launcher}glmark2-es2 '
                       f'--off-screen --size {resolution} --frame-end finish --results fps:cpu '
                       '-b build:use-vbo=true:duration=4 -b shading:shading=phong:duration=4')
            if args.workload == 'simple-triangle':
                command = f'{launcher}/usr/local/bin/gpu-pixel-check --benchmark --size={resolution}'
            if args.driver:
                command = f'LIBGL_ALWAYS_SOFTWARE=1 GBM_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER={args.driver} ' + command
            measured = run(f'GLES2-{resolution}', ['su', 'julian', '-c', command], timeout=30)
            unsupported = 'TGSI UNIMPLEMENTED' in measured['output']
            measured['driver_reported_unsupported_shaders'] = unsupported
            selection_verified = (not args.driver or
                                  f'renderer={args.driver}' in measured['output'] or
                                  f'GL_RENDERER:    {args.driver}' in measured['output'])
            measured['requested_driver_selection_verified'] = bool(selection_verified)
            measured['valid_graphics_performance_result'] = (
                not measured['timed_out'] and not unsupported and selection_verified and
                (measured['exit_code'] == 0 or
                 (args.driver == 'softpipe' and args.workload == 'simple-triangle' and measured['exit_code'] == 2)) and
                (args.workload != 'simple-triangle' or 'pixel_check=PASS' in measured['output']))
            result['tests'].append(measured)
    result['final'] = snapshot()
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f'Report: {args.output}', flush=True)


if __name__ == '__main__':
    main()
