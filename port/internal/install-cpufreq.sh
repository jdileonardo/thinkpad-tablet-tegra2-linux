#!/bin/sh
# Incremental installation on this Indigo; no kernel or boot-region writes.
set -eu
case "${1:---check}" in
    --check) apply=no ;;
    --apply) apply=yes ;;
    *) echo 'usage: install-cpufreq.sh [--check|--apply]' >&2; exit 2 ;;
esac
release=7.0.1-nura-indigo-ram
expected=6d6031809a52eb6a6841e8a0bb87ceede59460200fb8a5d7017e8d0733cfc106
source=/tmp/tegra20-cpufreq.ko
target=/lib/modules/$release/kernel/drivers/cpufreq/tegra20-cpufreq.ko
test "$(uname -r)" = "$release"
test "$(cat /sys/firmware/devicetree/base/model | tr -d '\000')" = 'Lenovo ThinkPad Tablet (Indigo)'
root_device=$(awk '$2 == "/" && $3 == "ext4" {print $1}' /proc/mounts)
test -n "$root_device"
root_disk=$(basename "$root_device" | sed 's/p[0-9]*$//')
test "$(cat "/sys/block/$root_disk/device/cid")" = 1101004d4d4333324703100a18dd6e00
case "$(readlink -f "/sys/block/$root_disk/device")" in
    */c8000600.mmc/*) ;;
    *) echo 'Root is not on the internal MMC controller' >&2; exit 1 ;;
esac
printf '%s  %s\n' "$expected" "$source" | sha256sum -c -
if test -f "$target"; then
    printf '%s  %s\n' "$expected" "$target" | sha256sum -c -
fi
test "$(modinfo -F vermagic "$source")" = '7.0.1-nura-indigo-ram SMP mod_unload modversions ARMv7 p2v8 '
echo CHECK_OK
test "$apply" = yes || exit 0
mkdir -p "$(dirname "$target")"
install -m 644 "$source" "$target"
depmod "$release"
modprobe tegra20-cpufreq
test "$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_driver)" = cpufreq-dt
test "$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor)" = ondemand
if ! grep -qx tegra20-cpufreq /etc/modules; then
    printf '\ntegra20-cpufreq\n' >> /etc/modules
fi
sync
printf '%s  %s\n' "$expected" "$target" | sha256sum -c -
modprobe --show-depends tegra20-cpufreq
echo INSTALL_OK
