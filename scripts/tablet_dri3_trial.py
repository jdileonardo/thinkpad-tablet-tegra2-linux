#!/usr/bin/env python3
"""Run a temporary private Xorg driver trial on the external-SD tablet."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import uuid

PREFIX = Path('/opt/indigo-xorg/dri3')
CONFIG = Path('/etc/lightdm/lightdm.conf.d/99-indigo-dri3-trial.conf')
COOKIE = Path('/tmp/indigo-dri3-trial.active')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path)
    parser.add_argument('--sha256')
    parser.add_argument('--restore')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Run from the tablet root diagnostic console')
    if args.restore:
        if COOKIE.exists() and COOKIE.read_text().strip() == args.restore:
            CONFIG.unlink(missing_ok=True)
            COOKIE.unlink()
            subprocess.run(['rc-service', 'lightdm', 'restart'], check=True)
            print('Original Xorg module path restored', flush=True)
        return
    if not args.module or not args.sha256:
        parser.error('--module and --sha256 are required')
    root_mount = next(line.split()[0] for line in Path('/proc/mounts').read_text().splitlines()
                      if line.split()[1] == '/')
    if root_mount != '/dev/mmcblk0p1' or 'c8000400.mmc' not in str(
            Path('/sys/class/block/mmcblk0/device').resolve()):
        raise SystemExit('Tablet is not running from the expected external SD')
    if CONFIG.exists() or COOKIE.exists():
        raise SystemExit('A DRI3 trial is already configured; restore it first')
    data = args.module.read_bytes()
    if hashlib.sha256(data).hexdigest() != args.sha256:
        raise SystemExit('Module SHA256 mismatch')
    module = PREFIX / 'lib/xorg/modules/drivers/opentegra_drv.so'
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_bytes(data)
    module.chmod(0o644)
    trial_script = PREFIX / 'trial.py'
    shutil.copyfile(Path(__file__), trial_script)
    token = uuid.uuid4().hex
    COOKIE.write_text(token + '\n')
    (PREFIX / 'trial-xorg.conf').write_text('Section "Module"\n'
                                           '    Load "exa"\nEndSection\n')
    CONFIG.write_text('[Seat:*]\nxserver-command=/usr/libexec/Xorg -modulepath '
                      '/opt/indigo-xorg/dri3/lib/xorg/modules,/usr/lib/xorg/modules '
                      '-config /opt/indigo-xorg/dri3/trial-xorg.conf\n')
    with Path('/tmp/indigo-dri3-restore.log').open('w') as log:
        subprocess.Popen(['sh', '-c', 'sleep 180; exec python3 "$1" --restore "$2"',
                          'dri3-restore', str(trial_script), token],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                         start_new_session=True)
    print(f'Trial token={token}; automatic restore in 180 seconds', flush=True)
    subprocess.run(['rc-service', 'lightdm', 'restart'], check=True)


if __name__ == '__main__':
    main()
