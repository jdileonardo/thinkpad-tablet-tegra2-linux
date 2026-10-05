#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
test "$(git -C sources/linux-historical rev-parse HEAD)" = 8b626d0a4f6f39a6c12bf6ea4ed61744e4f7a54e
rg -q '^CONFIG_ARM=y$' build/linux-historical/.config
docker run --rm --user "$(id -u):$(id -g)" -v "$project_root:/work" \
  thinkpad-port-build:2026-10-05 make -j8 -C /work/sources/linux-historical \
  O=/work/build/linux-historical ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- modules
mkdir -p build/ram-test/modules
for relative in drivers/video/backlight/backlight.ko \
    drivers/video/backlight/pwm_bl.ko drivers/gpu/drm/panel/panel-simple.ko \
    drivers/net/wireless/broadcom/brcm80211/brcmutil/brcmutil.ko \
    drivers/net/wireless/broadcom/brcm80211/brcmfmac/brcmfmac.ko; do
  cp "build/linux-historical/$relative" "build/ram-test/modules/${relative##*/}"
done
docker run --rm --user "$(id -u):$(id -g)" -v "$project_root:/work" \
  thinkpad-port-build:2026-10-05 sh -c \
  'arm-linux-gnueabihf-strip --strip-debug /work/build/ram-test/modules/*.ko'
sha256sum build/ram-test/modules/*.ko > build/ram-test/modules/SHA256SUMS
