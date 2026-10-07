#!/bin/sh
# Stage two: clean Linux user area. Boot areas remain protected and untouched.
set -eu
mode=${1:---check}
case "$mode" in --check|--apply) ;; *) exit 2 ;; esac
image=${2:-/var/tmp/indigo-internal-install/internal-user-area.img}
mbr=${3:-/tmp/expanded-mbr.bin}
trap 'result=$?; echo INTERNAL_INSTALL_EXIT=$result' EXIT
[ "$(id -u)" = 0 ]
[ "$(wc -c < "$image")" -eq 4296015872 ]
[ "$(wc -c < "$mbr")" -eq 512 ]
[ "$(sha256sum "$mbr" | cut -d ' ' -f 1)" = 05c4ad9419cabcb4a77e6d3f3682ac5e44858ea0eb64e7cab36cb3482e1b02b3 ]
rootdev=$(awk '$2=="/" {print $1}' /proc/mounts)
case "$(readlink -f "/sys/class/block/${rootdev##*/}")" in *c8000400.mmc*) ;; *) exit 1 ;; esac
[ "$(/bin/busybox blkid "$rootdev" | sed -n 's/.* UUID="\([^"]*\)".*/\1/p')" = 2a6e5a89-5a50-46c6-95ec-b718e7abd62b ]
emmc=
for node in /sys/class/block/mmcblk[0-9]*; do
    name=${node##*/}
    case "${name#mmcblk}" in ''|*[!0-9]*) continue ;; esac
    [ -f "$node/device/cid" ] || continue
    [ "$(cat "$node/device/cid")" = 1101004d4d4333324703100a18dd6e00 ] || continue
    case "$(readlink -f "$node")" in *c8000600.mmc*) ;; *) continue ;; esac
    [ -z "$emmc" ] || exit 1
    emmc=/dev/$name
done
[ -n "$emmc" ]
emmc_name=${emmc##*/}
[ "$(cat "/sys/class/block/$emmc_name/size")" -eq 62521344 ]
awk -v dev="$emmc" '$1 ~ ("^" dev) {bad=1} END {exit bad}' /proc/mounts
for suffix in boot0 boot1; do
    [ "$(cat "/sys/class/block/$emmc_name$suffix/force_ro")" -eq 1 ]
done
check_boot_regions() {
    [ "$(sha256sum "${emmc}boot0" | cut -d ' ' -f 1)" = 0f16cc41acc0383839467b1c539c2de86ead52d6b4fb0f8bfc820c757881dc6d ]
    [ "$(sha256sum "${emmc}boot1" | cut -d ' ' -f 1)" = 92132a5db6f10c1eafd2e2437c32d3d966865ba534052bf284bf61b072ce6132 ]
}
check_boot_regions
[ "$(dd if="$emmc" bs=1M count=10 2>/dev/null | sha256sum | cut -d ' ' -f 1)" = e7363f61c81b70d54f4bfeb7fea9ee98e3d9f8b138f5cbcdcea670c8aba3c50e ]
echo INTERNAL_SOURCE_HASH_BEGIN
[ "$(sha256sum "$image" | cut -d ' ' -f 1)" = 5edc6763f85c754991be57e6a8dbcad3f054bd987f43d934f1bcdcdc0d162078 ]
printf 'INTERNAL_PRECHECK_OK: %s main area, offset 0, 4296015872 bytes\n' "$emmc"
if [ "$mode" = --check ]; then exit 0; fi
for tool in blockdev e2fsck resize2fs; do command -v "$tool" >/dev/null; done
# Repeat the mount check immediately before writing and after partition reload.
awk -v dev="$emmc" '$1 ~ ("^" dev) {bad=1} END {exit bad}' /proc/mounts
echo INTERNAL_WRITE_BEGIN
dd if="$image" of="$emmc" bs=1M count=4097 conv=fsync
sync
blockdev --flushbufs "$emmc"
echo INTERNAL_READBACK_BEGIN
[ "$(dd if="$emmc" bs=1M count=4097 2>/dev/null | sha256sum | cut -d ' ' -f 1)" = 5edc6763f85c754991be57e6a8dbcad3f054bd987f43d934f1bcdcdc0d162078 ]
echo INTERNAL_READBACK_OK
check_boot_regions
echo INTERNAL_EXPAND_BEGIN
dd if="$mbr" of="$emmc" bs=512 count=1 conv=fsync
sync
blockdev --rereadpt "$emmc"
sleep 2
partition=${emmc}p1
[ "$(cat "/sys/class/block/${partition##*/}/size")" -eq 62519296 ]
awk -v dev="$emmc" '$1 ~ ("^" dev) {bad=1} END {exit bad}' /proc/mounts
e2fsck -fn "$partition"
resize2fs "$partition"
e2fsck -fn "$partition"
[ "$(/bin/busybox blkid "$partition" | sed -n 's/.* UUID="\([^"]*\)".*/\1/p')" = a1b59fdc-49f7-46bb-b099-4c6012334c07 ]
check_boot_regions
sync
echo INTERNAL_INSTALL_AND_EXPANSION_OK
