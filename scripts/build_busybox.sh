#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
run_make() {
  docker run --rm --user "$(id -u):$(id -g)" -v "$project_root:/work" \
    thinkpad-port-build:2026-10-05 make -C sources/busybox-1.36.1 \
    O=/work/build/busybox CROSS_COMPILE=arm-linux-gnueabihf- "$@"
}
mkdir -p build/busybox
run_make defconfig
python3 - <<'PY'
from pathlib import Path
p=Path('build/busybox/.config')
s=p.read_text().replace('# CONFIG_STATIC is not set','CONFIG_STATIC=y')
p.write_text(s)
PY
run_make -j8
