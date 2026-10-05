#!/usr/bin/env bash
set -euo pipefail
project_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$project_root"
# Run on a fresh diagnostic RAM boot. All transfers target RAM-backed /tmp.
python3 scripts/ram_console.py --seconds 3 --command 'mkdir -p /tmp/firmware/brcm'
for name in backlight pwm_bl panel-simple brcmutil brcmfmac; do
  python3 scripts/ram_transfer.py upload "build/ram-test/modules/$name.ko" "/tmp/$name.ko"
done
for name in brcmfmac4329-sdio.bin brcmfmac4329-sdio.txt; do
  python3 scripts/ram_transfer.py upload "build/stock/firmware/$name" "/tmp/firmware/brcm/$name"
done
python3 scripts/ram_console.py --seconds 6 \
  --command '/bin/busybox insmod /tmp/backlight.ko' \
  --command '/bin/busybox insmod /tmp/pwm_bl.ko' \
  --command '/bin/busybox insmod /tmp/panel-simple.ko' \
  --command 'echo -n /tmp/firmware > /sys/module/firmware_class/parameters/path' \
  --command '/bin/busybox insmod /tmp/brcmutil.ko' \
  --command '/bin/busybox insmod /tmp/brcmfmac.ko' \
  --command 'sleep 2' --command 'ls /sys/class/drm' --command 'ls /sys/class/net'
