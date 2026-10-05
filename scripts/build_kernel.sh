#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
source_head=$(git -C sources/linux-historical rev-parse HEAD)
test "$source_head" = 8b626d0a4f6f39a6c12bf6ea4ed61744e4f7a54e
python3 scripts/prepare_kernel.py
run_make() {
  docker run --rm --user "$(id -u):$(id -g)" -v "$project_root:/work" \
    thinkpad-port-build:2026-10-05 make -C sources/linux-historical \
    O=/work/build/linux-historical ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- "$@"
}
run_make phj00_defconfig
for feature in USB_GADGET USB_CHIPIDEA USB_CHIPIDEA_UDC USB_CONFIGFS \
    USB_CONFIGFS_ACM CONFIGFS_FS DEVTMPFS DEVTMPFS_MOUNT BLK_DEV_INITRD \
    RD_GZIP FRAMEBUFFER_CONSOLE IKCONFIG_PROC ARM_APPENDED_DTB ARM_ATAG_DTB_COMPAT; do
  sources/linux-historical/scripts/config --file build/linux-historical/.config --enable "$feature"
done
sources/linux-historical/scripts/config --file build/linux-historical/.config \
  --set-str LOCALVERSION '-thinkpad-ram'
run_make olddefconfig
run_make -j8 zImage tegra20-lenovo-indigo.dtb
sha256sum build/linux-historical/arch/arm/boot/zImage \
  build/linux-historical/arch/arm/boot/dts/tegra20-lenovo-indigo.dtb \
  > build/linux-historical/SHA256SUMS
