#!/usr/bin/env python3
"""Apply the tracked Indigo additions to the pinned current Tegra source."""
import json
import shutil
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / 'sources/linux-nura'
lock = json.loads((root / 'sources.lock.json').read_text())
actual = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
if actual != lock['linux-nura']['commit']:
    raise SystemExit('Current Tegra source does not match sources.lock.json')
for name in ('0001-panel-simple-add-indigo-panel.patch',
             '0002-grate-sync-only-streaming-dma-bufs.patch'):
    patch = root / 'port' / name
    check = subprocess.run(['git', '-C', str(source), 'apply', '--check', str(patch)], capture_output=True)
    if check.returncode == 0:
        subprocess.run(['git', '-C', str(source), 'apply', str(patch)], check=True)
    elif subprocess.run(['git', '-C', str(source), 'apply', '--reverse', '--check', str(patch)], capture_output=True).returncode:
        raise SystemExit(f'Kernel source differs from both the pinned original and {name}')
dts_dir = source / 'arch/arm/boot/dts/nvidia'
shutil.copyfile(root / 'port/tegra20-lenovo-indigo.dts', dts_dir / 'tegra20-lenovo-indigo.dts')
makefile = dts_dir / 'Makefile'
text = makefile.read_text()
line = 'dtb-$(CONFIG_ARCH_TEGRA_2x_SOC) += tegra20-lenovo-indigo.dtb\n'
if line not in text:
    makefile.write_text(text + '\n' + line)
print('Prepared Indigo device tree, panel driver and Grate DMA-BUF cache synchronization.')
