#!/usr/bin/env python3
"""Build the ARMv7 XFCE/OpenRC rootfs in Docker; no media writes."""
import argparse
import json
import os
import secrets
import shutil
import subprocess
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--container', action='store_true', help=argparse.SUPPRESS)
args = parser.parse_args()
project = Path(__file__).resolve().parents[1]
if not args.container:
    lock = json.loads((project / 'sources.lock.json').read_text())
    for source in ('pmaports', 'pmbootstrap'):
        actual = subprocess.check_output(['git', '-C', str(project / 'sources' / source),
                                          'rev-parse', 'HEAD'], text=True).strip()
        if actual != lock[source]['commit']:
            raise SystemExit(f'{source} differs from the pinned source revision')
    build = project / 'build'
    build.mkdir(exist_ok=True)
    shutil.copyfile(project / 'port/pmbootstrap.cfg', build / 'pmbootstrap.cfg')
    work = build / 'pmbootstrap'
    work.mkdir(exist_ok=True)
    if not (work / 'version').exists():
        if any(work.iterdir()):
            raise SystemExit('Existing unversioned work directory needs inspection')
        (work / 'version').write_text('8\n')  # pinned pmbootstrap 3.11.1 work format
    (work / 'cache_git').mkdir(exist_ok=True)
    password = build / 'nura-first-login.txt'
    if not password.exists():
        fd = os.open(password, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as output:
            output.write(secrets.token_urlsafe(12) + '\n')
    if Path('/proc/sys/fs/binfmt_misc/qemu-arm').exists():
        raise SystemExit('Existing host qemu-arm registration needs inspection before pmbootstrap')
    subprocess.run(['docker', 'run', '--rm', '--cap-add', 'SYS_ADMIN',
                    '--security-opt', 'apparmor=unconfined',
                    '-e', 'GIT_CONFIG_COUNT=2', '-e', 'GIT_CONFIG_KEY_0=safe.directory',
                    '-e', 'GIT_CONFIG_VALUE_0=/work/sources/pmaports',
                    '-e', 'GIT_CONFIG_KEY_1=safe.directory',
                    '-e', 'GIT_CONFIG_VALUE_1=/work/sources/pmbootstrap',
                    '-v', f'{project}:/work', 'thinkpad-pmbootstrap:2026-10-05',
                    'python3', '/work/scripts/build_nura_rootfs.py', '--container'], check=True)
else:
    subprocess.run(['mount', '-t', 'binfmt_misc', 'binfmt_misc',
                    '/proc/sys/fs/binfmt_misc'], check=True)
    pmb = ['python3', '/work/sources/pmbootstrap/pmbootstrap.py', '--as-root',
           '-c', '/work/build/pmbootstrap.cfg', '-y']
    password = (project / 'build/nura-first-login.txt').read_text().strip()
    try:
        subprocess.run(pmb + ['install', '--no-image', '--password', password], check=True)
    finally:
        subprocess.run(pmb + ['shutdown'], check=True)
