#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
build_output=uboot-ram
build_config=thinkpad_ram_defconfig
if [[ "${1:-}" == "--direct-linux" ]]; then
  build_output=uboot-direct
elif [[ "${1:-}" == "--nura" ]]; then
  build_output=uboot-nura
elif [[ "${1:-}" == "--nura-sd" ]]; then
  build_output=uboot-nura-sd
elif [[ "${1:-}" == "--nura-storage-test" ]]; then
  build_output=uboot-nura-storage-test
  build_config=thinkpad_storage_test_defconfig
elif [[ "${1:-}" == "--nura-storage" ]]; then
  build_output=uboot-nura-storage
  build_config=thinkpad_storage_defconfig
fi
python3 scripts/prepare_uboot.py "$@"
builder_id=sha256:bdeae42b66b5d1d1a70fe3f1505a17ba156eca8efdfa8364e9db3411e06beb2c
docker image inspect "$builder_id" >/dev/null
docker run --rm --user "$(id -u):$(id -g)" -v "$project_root:/work" \
  "$builder_id" \
  make -C sources/u-boot-historical O="/work/build/$build_output" \
  CROSS_COMPILE=arm-linux-gnueabihf- PYTHON=python2 "$build_config"
docker run --rm --user "$(id -u):$(id -g)" -v "$project_root:/work" \
  "$builder_id" \
  make -j8 -C sources/u-boot-historical O="/work/build/$build_output" \
  CROSS_COMPILE=arm-linux-gnueabihf- PYTHON=python2
sha256sum "build/$build_output/u-boot-dtb-tegra.bin" > "build/$build_output/SHA256SUMS"
