#!/usr/bin/env python3
"""Package reviewed extra modules and verify their image integration."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def selected_modules(lock):
    modules = lock.get('extra_kernel_modules', {})
    for target, entry in modules.items():
        path = Path(target)
        source = Path(entry['source'])
        if (not path.parts or path.is_absolute() or '..' in path.parts or path.parts[0] != 'kernel'
                or path.suffix != '.ko' or not source.parts or source.is_absolute()
                or '..' in source.parts or source.parts[0] != 'build'):
            raise ValueError(f'Invalid module path: {target}')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', entry['autoload']):
            raise ValueError(f'Invalid autoload name: {target}')
        if lock['files'].get(str(source)) != entry['tested_module_sha256']:
            raise ValueError(f'Module differs from tested checkpoint: {target}')
        if lock['files']['build/linux-nura/arch/arm/boot/zImage'] != entry['tested_kernel_sha256']:
            raise ValueError(f'Kernel differs from module test checkpoint: {target}')
    return modules


def install(root, project, lock, release):
    modules = selected_modules(lock)
    for target, entry in modules.items():
        source = project / entry['source']
        if hashlib.sha256(source.read_bytes()).hexdigest() != lock['files'][entry['source']]:
            raise ValueError(f'Module input hash mismatch: {source}')
        vermagic = subprocess.check_output(['modinfo', '-F', 'vermagic', str(source)], text=True)
        if not vermagic.startswith(release + ' '):
            raise ValueError(f'Module release mismatch: {source}')
        destination = root / 'lib/modules' / release / target
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        destination.chmod(0o644)
        for name, value in ((root / 'etc/modules', entry['autoload']),
                            (root / 'lib/modules' / release / 'modules.order', target)):
            lines = name.read_text().splitlines() if name.exists() else []
            if value not in lines:
                name.parent.mkdir(parents=True, exist_ok=True)
                name.write_text('\n'.join([*lines, value]) + '\n')


def verify(read, lock, release):
    checked = {}
    modules = selected_modules(lock)
    if not modules:
        return checked
    prefix = f'/usr/lib/modules/{release}/'
    autoload = read('/etc/modules').decode().splitlines()
    order = read(prefix + 'modules.order').decode().splitlines()
    dependencies = read(prefix + 'modules.dep').decode().splitlines()
    aliases = read(prefix + 'modules.alias').decode().splitlines()
    for target, entry in modules.items():
        path = prefix + target
        actual = hashlib.sha256(read(path)).hexdigest()
        if actual != lock['files'][entry['source']]:
            raise ValueError(f'Installed module hash mismatch: {path}')
        if entry['autoload'] not in autoload or target not in order:
            raise ValueError(f'Module startup configuration missing: {target}')
        if not any(line.startswith(target + ':') for line in dependencies):
            raise ValueError(f'Module dependency index missing: {target}')
        alias = f"alias {entry['modalias']} {entry['autoload'].replace('-', '_')}"
        if alias not in aliases:
            raise ValueError(f'Module device alias missing: {target}')
        checked[path] = actual
    return checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--project', required=True, type=Path)
    parser.add_argument('--lock', required=True, type=Path)
    parser.add_argument('--release', required=True)
    args = parser.parse_args()
    install(args.root, args.project, json.loads(args.lock.read_text()), args.release)


if __name__ == '__main__':
    main()
