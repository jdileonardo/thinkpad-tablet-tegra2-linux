#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
builder_image=thinkpad-nura-build:2026-10-05
if [[ -f port/image-inputs.lock.json ]]; then
  builder_image=$(python3 scripts/pinned_build_container.py "$builder_image")
fi
python3 scripts/prepare_nura_kernel.py
python3 - <<'PY'
import json, subprocess, shutil
from pathlib import Path
lock = json.loads(Path('sources.lock.json').read_text())
actual = subprocess.check_output(['git', '-C', 'sources/pmaports', 'rev-parse', 'HEAD'], text=True).strip()
assert actual == lock['pmaports']['commit'], 'Package tree revision differs from lock file'
Path('build/linux-nura').mkdir(parents=True, exist_ok=True)
shutil.copyfile('sources/pmaports/device/testing/linux-postmarketos-grate/config-postmarketos-grate.armv7', 'build/linux-nura/.config')
PY
for feature in USB_CONFIGFS USB_LIBCOMPOSITE USB_U_SERIAL USB_F_ACM \
    USB_CONFIGFS_ACM RFKILL CFG80211 BRCMUTIL BRCMFMAC IKCONFIG_PROC DEVTMPFS_MOUNT; do
  sources/linux-nura/scripts/config --file build/linux-nura/.config --enable "$feature"
done
# Keep this bootstrap small; distribution packaging can retain full debug info.
for feature in DEBUG_INFO DEBUG_INFO_DWARF5 DEBUG_INFO_BTF DEBUG_INFO_BTF_MODULES; do
  sources/linux-nura/scripts/config --file build/linux-nura/.config --disable "$feature"
done
sources/linux-nura/scripts/config --file build/linux-nura/.config --enable DEBUG_INFO_NONE
sources/linux-nura/scripts/config --file build/linux-nura/.config \
  --set-str LOCALVERSION '-nura-indigo-ram'
run_make() {
  docker run --rm --network none --user "$(id -u):$(id -g)" -v "$project_root:/work" \
    "$builder_image" make -C /work/sources/linux-nura \
    O=/work/build/linux-nura ARCH=arm LLVM=1 "$@"
}
run_make olddefconfig
for feature in USB_CONFIGFS_ACM RFKILL CFG80211 BRCMUTIL BRCMFMAC; do
  if ! rg -q "^CONFIG_${feature}=y$" build/linux-nura/.config; then
    echo "Required bootstrap feature is not built in: $feature" >&2
    exit 1
  fi
done
run_make -j8 zImage nvidia/tegra20-lenovo-indigo.dtb
run_make -j8 drivers/input/evdev.ko drivers/hid/hid-generic.ko drivers/hid/usbhid/usbhid.ko \
  drivers/reset/reset-gpio.ko
bash scripts/build_ntrig_module.sh
sha256sum build/linux-nura/arch/arm/boot/zImage \
  build/linux-nura/arch/arm/boot/dts/nvidia/tegra20-lenovo-indigo.dtb \
  > build/linux-nura/SHA256SUMS
