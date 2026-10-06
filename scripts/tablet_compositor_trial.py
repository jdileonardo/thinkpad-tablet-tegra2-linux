#!/usr/bin/env python3
"""Run a bounded nested Weston GL trial as the tablet desktop user."""
import argparse
import os
from pathlib import Path
import re
import signal
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label', default='weston-pixels')
    parser.add_argument('--software', action='store_true')
    args = parser.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', args.label):
        raise SystemExit('Use a simple filename label')
    if os.getuid() != 10000:
        raise SystemExit('Run as the Indigo desktop user julian (uid 10000)')
    root_device = next(line.split()[0] for line in Path('/proc/mounts').read_text().splitlines()
                       if line.split()[1] == '/')
    if 'c8000400.mmc' not in str((Path('/sys/class/block') / Path(root_device).name).resolve()):
        raise SystemExit('Expected the external SD root')
    cookie = Path('/tmp/indigo-dri3-trial.active')
    if not cookie.exists() or cookie.stat().st_mtime + 180 - time.time() < 70:
        raise SystemExit('Start a fresh DRI3 trial first; need at least 70 seconds before automatic restore')
    prefix = Path('/tmp') / args.label
    if any(prefix.with_suffix(suffix).exists()
           for suffix in ('.log', '.stderr.log', '.pixels.log', '.ppm')):
        raise SystemExit('Trial output already exists; choose a fresh label')
    env = dict(os.environ, DISPLAY=':0', XAUTHORITY='/home/julian/.Xauthority',
               XDG_RUNTIME_DIR='/run/user/10000', WAYLAND_DISPLAY=args.label,
               INDIGO_MESA_REVISION='ad06de32d309')
    if args.software:
        env.update(LIBGL_ALWAYS_SOFTWARE='1', GBM_ALWAYS_SOFTWARE='1', GALLIUM_DRIVER='softpipe')
    for name in ('LIBGL_ALWAYS_SOFTWARE', 'GBM_ALWAYS_SOFTWARE', 'GALLIUM_DRIVER'):
        if not args.software:
            env.pop(name, None)
    log = prefix.with_suffix('.log')
    process = None
    try:
        with prefix.with_suffix('.stderr.log').open('w') as stderr:
            process = subprocess.Popen([
                '/usr/local/bin/indigo-gpu-run', '/sbin/weston', '--backend=x11',
                '--renderer=gl', '--width=640', '--height=480', '--socket=' + args.label,
                '--no-config', '--idle-time=0', '--log=' + str(log)],
                env=env, stdin=subprocess.DEVNULL, stdout=stderr, stderr=stderr,
                start_new_session=True)
            deadline = time.monotonic() + 20
            window = None
            while time.monotonic() < deadline:
                content = log.read_text() if log.exists() else ''
                match = re.search(r'x11 output 640x480, window id (\d+)', content)
                if match:
                    window = match.group(1)
                    break
                if process.poll() is not None:
                    raise RuntimeError(f'Weston exited {process.returncode}: {content}')
                time.sleep(0.2)
            if window is None:
                raise RuntimeError('Weston did not create its X11 output in 20 seconds')
            expected = 'GL renderer: softpipe' if args.software else 'GL renderer: Tegra'
            if expected not in content or 'Using GL renderer' not in content:
                raise RuntimeError('Unexpected renderer: ' + content)
            print(f'Weston pid={process.pid} X11 window={window} renderer={expected}', flush=True)
            with prefix.with_suffix('.pixels.log').open('w') as pixels:
                fixture = subprocess.Popen(['/tmp/indigo-dri3/wayland-compositor-check', window],
                                           env=env, stdout=pixels, stderr=subprocess.STDOUT)
                try:
                    deadline = time.monotonic() + 30
                    while fixture.poll() is None and time.monotonic() < deadline:
                        if 'RESULT PASS' in prefix.with_suffix('.pixels.log').read_text():
                            break
                        time.sleep(0.1)
                    # Capture while the last passing surface is still visible.
                    subprocess.run(['/tmp/indigo-dri3/x-window-capture', window,
                                    str(prefix.with_suffix('.ppm'))], env=env, check=True, timeout=10)
                    fixture.wait(timeout=max(1, deadline - time.monotonic()))
                finally:
                    if fixture.poll() is None:
                        fixture.kill()
                        fixture.wait()
            if fixture.returncode:
                raise RuntimeError(f'Pixel fixture failed: {prefix.with_suffix(".pixels.log").read_text()}')
            print(prefix.with_suffix('.pixels.log').read_text(), end='', flush=True)
    finally:
        if process is not None:
            try:
                # Let Weston shut its shell clients down in its own order.
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


if __name__ == '__main__':
    main()
