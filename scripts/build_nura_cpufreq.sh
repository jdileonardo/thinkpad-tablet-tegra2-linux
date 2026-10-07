#!/usr/bin/env bash
# Build the missing module against the existing, configured Indigo kernel.
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
test "$(cat build/linux-nura/include/config/kernel.release)" = 7.0.1-nura-indigo-ram
rg -q '^CONFIG_ARM_TEGRA20_CPUFREQ=m$' build/linux-nura/.config
builder_image=$(python3 scripts/pinned_build_container.py thinkpad-nura-build:2026-10-05)
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$project_root:/work" \
  "$builder_image" make -j4 -C /work/sources/linux-nura \
  O=/work/build/linux-nura ARCH=arm LLVM=1 drivers/cpufreq/tegra20-cpufreq.ko
python3 - <<'PY'
import hashlib
import json
from pathlib import Path
import subprocess

root = Path('build/linux-nura')
files = ('drivers/cpufreq/tegra20-cpufreq.ko', 'arch/arm/boot/zImage',
         'arch/arm/boot/dts/nvidia/tegra20-lenovo-indigo.dtb', '.config')
manifest = {
    'kernel_release': (root / 'include/config/kernel.release').read_text().strip(),
    'builder': subprocess.check_output([
        'python3', 'scripts/pinned_build_container.py',
        'thinkpad-nura-build:2026-10-05'], text=True).strip(),
    'source_base': subprocess.check_output([
        'git', '-C', 'sources/linux-nura', 'rev-parse', 'HEAD'], text=True).strip(),
    'source_diff_sha256': hashlib.sha256(subprocess.check_output([
        'git', '-C', 'sources/linux-nura', 'diff', 'HEAD'])).hexdigest(),
    'source_branch_checkpoint': 'docs/source-branches-checkpoint.json',
    'files': {str(root / name): hashlib.sha256((root / name).read_bytes()).hexdigest()
              for name in files},
}
output = root / 'cpufreq-module-manifest.json'
output.write_text(json.dumps(manifest, indent=2) + '\n')
print(output.read_text())
PY
