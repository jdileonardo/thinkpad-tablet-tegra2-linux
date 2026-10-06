#!/usr/bin/env python3
"""Select a verified Indigo Xorg module on the external SD; retain stock rollback."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess

PREFIX = Path('/opt/indigo-xorg/xfce')
CONFIG = Path('/etc/lightdm/lightdm.conf.d/95-indigo-xorg.conf')
SETTINGS = ('[Seat:*]\nxserver-command=/usr/libexec/Xorg -modulepath '
            '/opt/indigo-xorg/xfce/lib/xorg/modules,/usr/lib/xorg/modules '
            '-config /opt/indigo-xorg/xfce/indigo-xorg.conf\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path)
    parser.add_argument('--sha256')
    parser.add_argument('--restore-stock', action='store_true')
    args = parser.parse_args()
    root = next(line.split()[0] for line in Path('/proc/mounts').read_text().splitlines()
                if line.split()[1] == '/')
    if os.geteuid() != 0 or 'c8000400.mmc' not in str(
            (Path('/sys/class/block') / Path(root).name).resolve()):
        raise SystemExit('Run as root on the verified external SD Indigo system')
    if Path('/tmp/indigo-dri3-trial.active').exists() or Path(
            '/etc/lightdm/lightdm.conf.d/99-indigo-dri3-trial.conf').exists():
        raise SystemExit('Restore the temporary driver trial before installing')
    if CONFIG.exists() and CONFIG.read_text() != SETTINGS:
        raise SystemExit('Existing module selection is not owned by this installer')
    if args.restore_stock:
        if args.module or args.sha256:
            parser.error('--restore-stock cannot be combined with a module')
        CONFIG.unlink(missing_ok=True)
        subprocess.run(['rc-service', 'lightdm', 'restart'], check=True)
        print('Distribution Xorg module path restored; private artifacts retained', flush=True)
        return
    if not args.module or not args.sha256:
        parser.error('--module and --sha256 are required')
    data = args.module.read_bytes()
    if hashlib.sha256(data).hexdigest() != args.sha256:
        raise SystemExit('Module SHA256 mismatch')
    module = PREFIX / 'lib/xorg/modules/drivers/opentegra_drv.so'
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_bytes(data)
    module.chmod(0o644)
    (PREFIX / 'indigo-xorg.conf').write_text('Section "Module"\n    Load "exa"\nEndSection\n')
    CONFIG.write_text(SETTINGS)
    try:
        subprocess.run(['rc-service', 'lightdm', 'restart'], check=True)
    except Exception:
        CONFIG.unlink(missing_ok=True)
        subprocess.run(['rc-service', 'lightdm', 'restart'], check=False)
        raise
    print(f'Private XFCE module selected: SHA256 {args.sha256}', flush=True)


if __name__ == '__main__':
    main()
