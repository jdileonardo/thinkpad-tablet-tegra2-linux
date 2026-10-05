#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
build_output=uboot-ram
if [[ "${1:-}" == "--direct-linux" ]]; then
  build_output=uboot-direct
fi
python3 scripts/prepare_uboot.py "$@"
docker run --rm --user "$(id -u):$(id -g)" -v "$project_root:/work" \
  thinkpad-port-build:2026-10-05 \
  make -C sources/u-boot-historical O="/work/build/$build_output" \
  CROSS_COMPILE=arm-linux-gnueabihf- PYTHON=python2 thinkpad_ram_defconfig
docker run --rm --user "$(id -u):$(id -g)" -v "$project_root:/work" \
  thinkpad-port-build:2026-10-05 \
  make -j8 -C sources/u-boot-historical O="/work/build/$build_output" \
  CROSS_COMPILE=arm-linux-gnueabihf- PYTHON=python2
sha256sum "build/$build_output/u-boot-dtb-tegra.bin" > "build/$build_output/SHA256SUMS"
