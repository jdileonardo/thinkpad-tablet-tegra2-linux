import gzip
import json
from pathlib import Path
import re
import runpy
import subprocess
import time

helpers = runpy.run_path('/tmp/tablet-graphics-memory-trial.py', run_name='capture_helpers')
result = helpers['desktop_command'](['python3', '-c', "import runpy; m=runpy.run_path('/usr/local/bin/indigo-rotate',run_name='capture_rotation'); m['rotate']('left')"])
if result.returncode:
    raise RuntimeError(result.stdout + result.stderr)
with Path('/tmp/fixed-calendar-capture-widget.log').open('w') as log:
    process = subprocess.Popen(['su', 'julian', '-c', 'DISPLAY=:0 XAUTHORITY=/home/julian/.Xauthority GDK_BACKEND=x11 python3 /tmp/tablet-gtk-calendar-trial.py --seconds 40 --output /tmp/fixed-calendar-capture-widget.json'], stdout=log, stderr=log, start_new_session=True)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            match = re.search(r'^CALENDAR_DRAWN window=(\d+)$', Path('/tmp/fixed-calendar-capture-widget.log').read_text(), re.M)
            if match:
                break
            time.sleep(.25)
        else:
            raise RuntimeError('Calendar window not ready')
        time.sleep(2)
        capture = helpers['desktop_command'](['/tmp/xfce-window-capture', match[1], '/tmp/fixed-calendar-window.ppm'])
        if capture.returncode:
            raise RuntimeError(capture.stdout + capture.stderr)
        print(capture.stdout, flush=True)
        subprocess.run(['/tmp/graphics-stack-check', '--capture', '/tmp/fixed-calendar-scanout.ppm'], check=True)
        for kind in ('window', 'scanout'):
            path = Path(f'/tmp/fixed-calendar-{kind}.ppm')
            path.with_suffix('.ppm.gz').write_bytes(gzip.compress(path.read_bytes()))
        print('CAPTURES_READY', flush=True)
        process.wait(timeout=65)
        if process.returncode:
            raise RuntimeError('Calendar fixture failed')
        print('FIXTURE_CLOSED', flush=True)
    finally:
        if process.poll() is None:
            import os, signal
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
