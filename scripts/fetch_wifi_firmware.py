#!/usr/bin/env python3
"""Fetch the pinned Linux BCM4329 firmware and license; verify every byte."""
import base64
import hashlib
import json
import urllib.request
from pathlib import Path

project = Path(__file__).resolve().parents[1]
source = json.loads((project / 'sources.lock.json').read_text())['linux-firmware']
out = project / 'build/linux-firmware'
out.mkdir(parents=True, exist_ok=True)
for name, digest in source['files'].items():
    path = out / Path(name).name
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
        continue
    url = f"{source['url']}/+/{source['commit']}/{name}?format=TEXT"
    data = base64.b64decode(urllib.request.urlopen(url, timeout=60).read(), validate=False)
    if hashlib.sha256(data).hexdigest() != digest:
        raise SystemExit(f'Firmware integrity check failed: {name}')
    path.write_bytes(data)
    print(f'Verified {name}: {len(data)} bytes')
