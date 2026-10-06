#!/usr/bin/env python3
"""Export locked binary inputs and Docker images, excluding local credentials."""
import gzip
import hashlib
import json
import shutil
import subprocess
import tarfile
from pathlib import Path


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    project = Path(__file__).resolve().parents[1]
    lock_path = project / 'port/image-inputs.lock.json'
    lock = json.loads(lock_path.read_text())
    output = project / 'build/image-inputs'
    inputs = output / 'frozen-inputs.tar'
    containers = output / 'containers.tar.gz'
    if inputs.exists() or containers.exists():
        raise SystemExit('Exports exist; refusing to replace them')
    for name, expected in lock['files'].items():
        path = (project / name).resolve()
        if not path.is_relative_to(project) or digest(path) != expected:
            raise SystemExit(f'Frozen input differs: {name}')
    # Archives are numeric-owner snapshots. The local login password and active
    # Wi-Fi profile are deliberately absent from the lock and this export.
    with tarfile.open(inputs, 'w') as archive:
        for name in ['port/image-inputs.lock.json', *lock['files']]:
            archive.add(project / name, arcname=name, recursive=False)
    print('Locked input archive exported', flush=True)
    with containers.open('xb') as raw:
        with gzip.GzipFile(fileobj=raw, mode='wb', compresslevel=1, mtime=0) as target:
            process = subprocess.Popen(['docker', 'save', *lock['containers'].values()],
                                       stdout=subprocess.PIPE)
            try:
                shutil.copyfileobj(process.stdout, target, 8 * 1024 * 1024)
            finally:
                process.stdout.close()
            if process.wait():
                raise SystemExit('Docker image export failed; discard partial exports')
    manifest = {'input_lock_sha256': digest(lock_path), 'containers': lock['containers'],
                'files': {p.name: digest(p) for p in (inputs, containers)},
                'private_login_password_and_wifi_profile_exported': False,
                'restore': ['Extract frozen-inputs.tar at the project root',
                            'docker load < containers.tar.gz',
                            'Provide a private login password file and optionally a Wi-Fi keyfile',
                            'Run scripts/create_nura_sd_image.py with a new output directory']}
    (output / 'export-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print('Docker images exported; both archives SHA256 recorded', flush=True)


if __name__ == '__main__':
    main()
