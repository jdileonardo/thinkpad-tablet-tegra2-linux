#!/usr/bin/env python3
"""Bounded native DRM Weston trial; always return to the SD's XFCE desktop."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import uuid

COOKIE = Path('/run/indigo-native-weston-trial.json')
LOCK = Path('/run/indigo-native-weston-trial.lock')


def check_capture(path, transform):
    # rotate-90 maps the fixture's logical left/right to physical bottom/top.
    # Both clients deliberately settle on exactly the same opaque pattern.
    with path.open('rb') as capture:
        if capture.readline() != b'P6\n' or capture.readline() != b'1280 800\n' \
                or capture.readline() != b'255\n':
            return False
        pixels = capture.read()
    if transform == 'rotate-90':
        expected = bytes((0, 0, 255)) * (1280 * 400) + bytes((255, 0, 0)) * (1280 * 400)
    else:
        expected = (bytes((255, 0, 0)) * 640 + bytes((0, 0, 255)) * 640) * 800
    return pixels == expected


def restore(token):
    with LOCK.open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not COOKIE.exists():
            return
        state = json.loads(COOKIE.read_text())
        if state['token'] != token:
            return
        for pid in reversed(state['groups']):
            try:
                os.killpg(pid, signal.SIGTERM)
                # Keep seatd alive while Weston releases its devices.
                time.sleep(2)
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        subprocess.run(['rc-service', 'lightdm', 'start'], check=True, timeout=30)
        COOKIE.unlink()
        print('Native trial ended; LightDM/XFCE restored', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='weston-native')
    parser.add_argument('--seconds', type=int, default=12)
    parser.add_argument('--software', action='store_true')
    client_group = parser.add_mutually_exclusive_group()
    client_group.add_argument('--egl-client', action='store_true',
                              help='Run the hardware Wayland client and capture its final scanout')
    client_group.add_argument('--qml-client', action='store_true',
                              help='Run Qt Quick through the OpenGL scene graph and capture scanout')
    parser.add_argument('--qml-software', action='store_true',
                        help='Use a CPU Qt Quick client as a reference; Weston still uses its selected renderer')
    parser.add_argument('--egl-draw', action='store_true',
                        help='Exercise matrices, short vertex attributes and indexed drawing in the EGL client')
    parser.add_argument('--egl-rgb565', action='store_true',
                        help='Select the 16-bit EGL buffer format used by the Qt client')
    parser.add_argument('--transform', choices=('normal', 'rotate-90'), default='rotate-90')
    parser.add_argument('--wayland-debug', action='store_true')
    parser.add_argument('--settle-seconds', type=float, default=2,
                        help='Allow the compositor to display the client final frame before capture')
    parser.add_argument('--restore')
    args = parser.parse_args()
    if args.qml_software and not args.qml_client:
        parser.error('--qml-software requires --qml-client')
    if args.egl_draw and not args.egl_client:
        parser.error('--egl-draw requires --egl-client')
    if args.egl_rgb565 and not args.egl_client:
        parser.error('--egl-rgb565 requires --egl-client')
    if not 0 <= args.settle_seconds <= 3:
        parser.error('--settle-seconds must be between 0 and 3')
    if os.geteuid() != 0:
        raise SystemExit('Run as root from the diagnostic console')
    if args.restore:
        restore(args.restore)
        return
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.label) or not 5 <= args.seconds <= 30:
        raise SystemExit('Use a simple label and a duration from 5 to 30 seconds')
    root = next(line.split()[0] for line in Path('/proc/mounts').read_text().splitlines()
                if line.split()[1] == '/')
    if 'c8000400.mmc' not in str((Path('/sys/class/block') / Path(root).name).resolve()):
        raise SystemExit('Expected the external SD root')
    prefix = Path('/tmp') / args.label
    if COOKIE.exists() or any(prefix.with_suffix(suffix).exists()
                              for suffix in ('.log', '.stderr.log', '.json')):
        raise SystemExit('A trial or its output already exists; restore or use a fresh label')
    if Path('/run/seatd.sock').exists():
        raise SystemExit('An existing seatd socket is present; do not replace another seat manager')
    if Path('/tmp/indigo-dri3-trial.active').exists():
        raise SystemExit('Restore the nested DRI3 trial before starting a native trial')
    subprocess.run(['rc-service', 'lightdm', 'status'], check=True)
    token = uuid.uuid4().hex
    state = {'token': token, 'groups': []}
    COOKIE.write_text(json.dumps(state))
    with Path('/tmp/indigo-native-weston-restore.log').open('w') as log:
        subprocess.Popen(['sh', '-c', 'sleep 90; exec python3 "$1" --restore "$2"',
                          'native-restore', str(Path(__file__).resolve()), token],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                         start_new_session=True)
    children = []
    try:
        subprocess.run(['rc-service', 'lightdm', 'stop'], check=True, timeout=30)
        runtime = Path('/run') / args.label
        runtime.mkdir(mode=0o700)
        env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime),
                   LIBSEAT_BACKEND='seatd', SEATD_SOCK='/run/seatd.sock',
                   SEATD_VTBOUND='0', INDIGO_MESA_REVISION='ad06de32d309')
        for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'LIBGL_ALWAYS_SOFTWARE',
                    'GBM_ALWAYS_SOFTWARE', 'GALLIUM_DRIVER'):
            env.pop(key, None)
        config = prefix.with_suffix('.ini')
        config.write_text('[core]\nidle-time=0\n'
                          '[output]\nname=DPI-1\ntransform=' + args.transform + '\n')
        before = Path('/proc/sys/kernel/tainted').read_text().strip()
        with prefix.with_suffix('.stderr.log').open('w') as stderr:
            def launch(command):
                process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                           stdout=stderr, stderr=stderr, start_new_session=True)
                children.append(process)
                state['groups'].append(process.pid)
                COOKIE.write_text(json.dumps(state))
                return process

            launch(['/sbin/seatd'])
            deadline = time.monotonic() + 5
            while not Path(env['SEATD_SOCK']).exists():
                if time.monotonic() > deadline:
                    raise RuntimeError('Private seatd did not start')
                time.sleep(0.1)
            renderer = 'pixman' if args.software else 'gl'
            command = ['/usr/local/bin/indigo-gpu-run', '/sbin/weston', '--backend=drm',
                       '--renderer=' + renderer, '--drm-device=card0',
                       '--socket=' + args.label, '--config=' + str(config),
                       '--log=' + str(prefix.with_suffix('.log'))]
            process = launch(command)
            client_result = None
            capture_result = None
            if args.egl_client or args.qml_client:
                socket = runtime / args.label
                deadline = time.monotonic() + 15
                while not socket.exists():
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError('Weston did not create a Wayland socket')
                    time.sleep(0.1)
                env['WAYLAND_DISPLAY'] = args.label
                if args.wayland_debug:
                    env['WAYLAND_DEBUG'] = '1'
                client_command = ['/usr/local/bin/indigo-gpu-run', '/tmp/wayland-egl-check']
                if args.egl_draw:
                    client_command.append('--draw')
                if args.egl_rgb565:
                    client_command.append('--rgb565')
                if args.qml_client:
                    env.update(QT_QPA_PLATFORM='wayland',
                               QT_WAYLAND_CLIENT_BUFFER_INTEGRATION='wayland-egl',
                               QSG_RHI_BACKEND='opengl', QSG_RENDER_LOOP='basic', QSG_INFO='1',
                               QT_LOGGING_RULES='qt.scenegraph.general=true;qt.rhi.*=true')
                    if args.qml_software:
                        env['QT_QUICK_BACKEND'] = 'software'
                        env.pop('QT_WAYLAND_CLIENT_BUFFER_INTEGRATION', None)
                    client_command = ['/usr/local/bin/indigo-gpu-run', '/usr/lib/qt6/bin/qmlscene',
                                      '/tmp/qt-wayland-scenegraph-check.qml']
                client_log = prefix.with_suffix('.client.log')
                with client_log.open('w') as output:
                    client = subprocess.Popen(client_command,
                                              env=env, stdin=subprocess.DEVNULL,
                                              stdout=output, stderr=output, start_new_session=True)
                    children.append(client)
                    state['groups'].append(client.pid)
                    COOKIE.write_text(json.dumps(state))
                    deadline = time.monotonic() + 20
                    while client.poll() is None and time.monotonic() < deadline:
                        if 'READY_CAPTURE' in client_log.read_text():
                            # A client swap/commit can precede the compositor's
                            # final scanout; do not sample an earlier animation.
                            time.sleep(args.settle_seconds)
                            with prefix.with_suffix('.capture.log').open('w') as capture:
                                capture_result = subprocess.run(
                                    ['/tmp/graphics-stack-check', '--capture', str(prefix.with_suffix('.ppm'))],
                                    stdout=capture, stderr=capture, timeout=8).returncode
                            break
                        time.sleep(0.1)
                    try:
                        client_result = client.wait(timeout=max(1, deadline - time.monotonic()))
                    except subprocess.TimeoutExpired:
                        client_result = 'timeout'
                result = process.poll()
            else:
                try:
                    result = process.wait(timeout=args.seconds)
                except subprocess.TimeoutExpired:
                    result = None
            report = {'command': command, 'seconds': args.seconds,
                      'output_transform': args.transform,
                      'exit_code_before_cleanup': result,
                      'client_exit_code': client_result, 'capture_exit_code': capture_result,
                      'kernel_taint_before': before,
                      'kernel_taint_after': Path('/proc/sys/kernel/tainted').read_text().strip()}
            if args.egl_client or args.qml_client:
                report['client_deadline_seconds'] = 20
                report['capture_settle_seconds'] = args.settle_seconds
                report['ready_for_capture'] = 'READY_CAPTURE' in client_log.read_text()
                report['qml_software_reference'] = args.qml_software
                report['scanout_matches_expected'] = (capture_result == 0 and
                                                       check_capture(prefix.with_suffix('.ppm'), args.transform))
            prefix.with_suffix('.json').write_text(json.dumps(report, indent=2) + '\n')
            print(json.dumps(report), flush=True)
            if result is not None:
                raise RuntimeError('Weston exited before bounded observation ended')
            if args.egl_client or args.qml_client:
                if client_result != 0 or capture_result != 0 or not report['ready_for_capture']:
                    raise RuntimeError('Client/capture failed; inspect the retained logs')
                if not report['scanout_matches_expected']:
                    raise RuntimeError('Scanout differs from the red/blue fixture; retained capture is a failure')
                if args.qml_client and not args.qml_software and 'VENDOR: Grate RENDERER: Tegra' not in client_log.read_text():
                    raise RuntimeError('Qt did not identify the hardware Tegra renderer')
    finally:
        restore(token)
        for process in children:
            process.wait(timeout=5)


if __name__ == '__main__':
    main()
