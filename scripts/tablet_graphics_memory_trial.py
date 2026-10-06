#!/usr/bin/env python3
"""Trace CMA/GEM allocation during bounded GTK calendar open/close cycles.

Uses a private tracefs instance and uniquely named probes, removed on exit.
Does not restart Xorg, drop caches, change CMA size or change desktop settings.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import signal
import subprocess
import time
import uuid

TRACE = Path('/sys/kernel/tracing')
EVENTS = ('bo_create', 'bo_return', 'bo_free')


def write(path, value):
    Path(path).write_text(value + '\n')


def probe_command(line):
    # tracefs control files reject the seek performed by Python append streams.
    fd = os.open(TRACE / 'kprobe_events', os.O_WRONLY | os.O_APPEND)
    try:
        payload = (line + '\n').encode()
        if os.write(fd, payload) != len(payload):
            raise RuntimeError('Short tracefs probe write')
    finally:
        os.close(fd)


def cleanup(name):
    if not re.fullmatch(r'indigo_gfx_[0-9a-f]{12}', name):
        raise ValueError('Invalid owned trace name')
    instance = TRACE / 'instances' / name
    if instance.exists():
        write(instance / 'tracing_on', '0')
        write(instance / 'events/enable', '0')
        instance.rmdir()
    for event in EVENTS:
        if (TRACE / 'events' / name / event).exists():
            probe_command(f'-:{name}/{event}')


def restore_rotation(name):
    state_path = Path('/tmp') / (name + '.rotation.json')
    if not state_path.exists():
        return
    state = json.loads(state_path.read_text())
    try:
        desktop_command(['python3', '-c',
            "import runpy; m=runpy.run_path('/usr/local/bin/indigo-rotate',run_name='rotation_probe'); "
            + f"m['rotate']({state['rotation']!r})"])
    finally:
        for process in state['watchers']:
            path = Path('/proc') / str(process['pid']) / 'stat'
            try:
                start = int(path.read_text().rsplit(')', 1)[1].split()[19])
                if start == process['start_ticks']:
                    os.kill(process['pid'], signal.SIGCONT)
            except (OSError, ValueError):
                pass
        state_path.unlink()


def snapshot(label, instance):
    write(instance / 'trace_marker', label)
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        if key in ('MemAvailable', 'CmaTotal', 'CmaFree', 'SwapTotal', 'SwapFree'):
            memory[key] = int(value.split()[0])
    return {'label': label, 'monotonic': time.monotonic(), 'memory_kib': memory,
            'drm_clients': (Path('/sys/kernel/debug/dri/0/clients')).read_text(),
            'framebuffers': (Path('/sys/kernel/debug/dri/0/framebuffers')).read_text()}


def desktop_command(arguments, timeout=15):
    # Use the live desktop bus; autolaunch would query a different session.
    for directory in Path('/proc').glob('[0-9]*'):
        try:
            # The session manager can change its bus after exec. A child's
            # exec-time environment reflects the bus actually used by XFCE.
            if (directory / 'comm').read_text().strip() != 'xfdesktop':
                continue
            environment = dict(item.split(b'=', 1) for item in
                               (directory / 'environ').read_bytes().split(b'\0') if b'=' in item)
            if environment.get(b'DISPLAY') != b':0':
                continue
            bus = environment[b'DBUS_SESSION_BUS_ADDRESS'].decode()
            command = ('DISPLAY=:0 XAUTHORITY=/home/julian/.Xauthority DBUS_SESSION_BUS_ADDRESS='
                       + shlex.quote(bus) + ' ' + shlex.join(arguments))
            process = subprocess.Popen(['su', 'julian', '-c', command],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, start_new_session=True)
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                try:
                    process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    process.stdout.close()
                    process.stderr.close()
                    process.wait(timeout=2)
                raise RuntimeError('Desktop command timed out: ' + shlex.join(arguments))
            return subprocess.CompletedProcess(arguments, process.returncode, stdout, stderr)
        except (OSError, KeyError):
            continue
    raise RuntimeError('Live XFCE session bus not found')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cleanup')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--cycles', type=int, default=6)
    parser.add_argument('--settle', type=int, default=45)
    parser.add_argument('--reload-desktop', action='store_true')
    parser.add_argument('--rotation-check', action='store_true')
    args = parser.parse_args()
    if args.cleanup:
        if not re.fullmatch(r'indigo_gfx_[0-9a-f]{12}', args.cleanup):
            parser.error('Invalid owned trace name')
        if (TRACE / 'instances' / args.cleanup).exists():
            try:
                restore_rotation(args.cleanup)
            finally:
                cleanup(args.cleanup)
        else:
            cleanup(args.cleanup)
        return
    if not args.output or not 1 <= args.cycles <= 8 or not 10 <= args.settle <= 90:
        parser.error('Use an output directory, 1..8 cycles and 10..90 settling seconds')
    root = next(line.split()[0] for line in Path('/proc/mounts').read_text().splitlines()
                if line.split()[1] == '/')
    if os.geteuid() != 0 or 'c8000400.mmc' not in str((Path('/sys/class/block') / Path(root).name).resolve()):
        raise RuntimeError('Run as root on the external-SD Indigo system')
    output = args.output.resolve()
    if not output.is_relative_to(Path('/tmp')) or output.exists():
        parser.error('Use a fresh directory under /tmp')
    output.mkdir()
    widgets = output / 'widgets'
    widgets.mkdir()
    desktop_user = pwd.getpwnam('julian')
    os.chown(widgets, desktop_user.pw_uid, desktop_user.pw_gid)
    name = 'indigo_gfx_' + uuid.uuid4().hex[:12]
    instance = TRACE / 'instances' / name
    report = {'trace_name': name, 'kernel': os.uname().release,
              'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'cycles': [], 'samples': [], 'kernel_before': subprocess.check_output(['dmesg'], text=True)}
    started = time.monotonic()
    try:
        instance.mkdir()
        write(instance / 'tracing_on', '0')
        write(instance / 'buffer_size_kb', '256')
        for event in ('cma_alloc_start', 'cma_alloc_finish', 'cma_release'):
            write(instance / 'events/cma' / event / 'enable', '1')
        # ARM32 tracefs lacks generic $argN fetches; AAPCS passes these in r1/r2.
        for line in (f'p:{name}/bo_create tegra_bo_create size=%r1:u32 flags=%r2:x32',
                     f'r:{name}/bo_return tegra_bo_create result=$retval:x32',
                     f'p:{name}/bo_free tegra_bo_free bo=%r1:x32'):
            probe_command(line)
        for event in EVENTS:
            write(instance / 'events' / name / event / 'enable', '1')
        with (output / 'watchdog.log').open('w') as log:
            subprocess.Popen(['sh', '-c', 'sleep 360; exec python3 "$1" --cleanup "$2"',
                              'graphics-trace-cleanup', str(Path(__file__).resolve()), name],
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             start_new_session=True)
        write(instance / 'tracing_on', '1')
        report['samples'].append(snapshot('baseline', instance))
        if args.reload_desktop:
            result = desktop_command(['xfdesktop', '--reload'])
            report['desktop_reload'] = {'exit_code': result.returncode, 'output': result.stdout + result.stderr}
            time.sleep(3)
            report['samples'].append(snapshot('after_desktop_reload', instance))
        if args.rotation_check:
            rotation_code = "import runpy; m=runpy.run_path('/usr/local/bin/indigo-rotate',run_name='rotation_probe'); "
            result = desktop_command(['python3', '-c', rotation_code + "print(m['display']()[1])"])
            original_rotation = result.stdout.strip().splitlines()[-1]
            if original_rotation not in ('normal', 'left', 'right', 'inverted'):
                raise RuntimeError('Cannot determine initial display rotation')
            watchers = []
            for directory in Path('/proc').glob('[0-9]*'):
                try:
                    command = (directory / 'cmdline').read_bytes().split(b'\0')
                    if b'/usr/local/bin/indigo-rotate' in command and b'watch' in command:
                        watchers.append({'pid': int(directory.name), 'start_ticks': int(
                            (directory / 'stat').read_text().rsplit(')', 1)[1].split()[19])})
                except (OSError, ValueError):
                    continue
            state_path = Path('/tmp') / (name + '.rotation.json')
            with state_path.open('x') as handle:
                json.dump({'rotation': original_rotation, 'watchers': watchers}, handle)
            state_path.chmod(0o600)
            for process in watchers:
                os.kill(process['pid'], signal.SIGSTOP)
            report['rotation_results'] = []
            for rotation in ('normal', 'left', 'inverted', 'right', original_rotation):
                result = desktop_command(['python3', '-c', rotation_code + f"m['rotate']({rotation!r})"])
                report['rotation_results'].append({'rotation': rotation, 'exit_code': result.returncode,
                                                   'output': result.stdout + result.stderr})
                if result.returncode:
                    raise RuntimeError('Rotation trial failed')
                time.sleep(2)
                report['samples'].append(snapshot('rotation_' + rotation, instance))
            restore_rotation(name)
        for cycle in range(args.cycles):
            if time.monotonic() - started > 170:
                raise RuntimeError('Trial time limit reached')
            label = f'cycle_{cycle + 1}'
            report['samples'].append(snapshot(label + '_before', instance))
            process = desktop_command(['env', 'GDK_BACKEND=x11', 'python3',
                '/tmp/tablet-gtk-calendar-trial.py', '--seconds', '10', '--output',
                str(widgets / f'widget-{cycle + 1}.json')], timeout=20)
            report['cycles'].append({'cycle': cycle + 1, 'exit_code': process.returncode,
                                     'output': process.stdout + process.stderr})
            if process.returncode:
                raise RuntimeError('Calendar cycle failed')
            report['samples'].append(snapshot(label + '_closed', instance))
            print(label + ' closed', flush=True)
            time.sleep(3)
        report['samples'].append(snapshot('settle_start', instance))
        time.sleep(args.settle)
        report['samples'].append(snapshot('settled', instance))
    except Exception as error:
        report['error'] = repr(error)
        raise
    finally:
        try:
            restore_rotation(name)
        except Exception as error:
            report['rotation_restore_error'] = repr(error)
        if instance.exists():
            write(instance / 'tracing_on', '0')
            (output / 'trace.txt').write_text((instance / 'trace').read_text())
            report['trace_stats'] = {str(path.relative_to(instance)): path.read_text()
                                     for path in (instance / 'per_cpu').glob('cpu*/stats')}
        report['kernel_after'] = subprocess.check_output(['dmesg'], text=True)
        report['elapsed_seconds'] = time.monotonic() - started
        cleanup(name)
        report['trace_cleanup_complete'] = not instance.exists() and not (TRACE / 'events' / name).exists()
        output.chmod(0o755)
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        print(f'Report: {output}/report.json', flush=True)


if __name__ == '__main__':
    main()
