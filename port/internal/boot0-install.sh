#!/bin/sh
# Stage-one installation only. Default is a read-only preflight.
set -eu
mode=${1:---check}
case "$mode" in --check|--apply) ;; *) echo 'Use --check or --apply' >&2; exit 2 ;; esac
image=${2:-/tmp/indigo-boot-region-padded.img}
expected_image=0f16cc41acc0383839467b1c539c2de86ead52d6b4fb0f8bfc820c757881dc6d
expected_old_boot0=8b5ba2a6e48071b990498a22720e0c3173e601789b35fec6c3520aadcd943c3b
expected_boot1=92132a5db6f10c1eafd2e2437c32d3d966865ba534052bf284bf61b072ce6132
expected_prefix=e7363f61c81b70d54f4bfeb7fea9ee98e3d9f8b138f5cbcdcea670c8aba3c50e
[ "$(id -u)" = 0 ]
[ -f "$image" ] && [ "$(wc -c < "$image")" -eq 2097152 ]
[ "$(sha256sum "$image" | cut -d ' ' -f 1)" = "$expected_image" ]
rootdev=$(awk '$2=="/" {print $1}' /proc/mounts)
case "$(readlink -f "/sys/class/block/${rootdev##*/}")" in
    *c8000400.mmc*) ;;
    *) echo 'The live root must be the recovery SD card' >&2; exit 1 ;;
esac
[ "$(/bin/busybox blkid "$rootdev" | sed -n 's/.* UUID="\([^"]*\)".*/\1/p')" = 2a6e5a89-5a50-46c6-95ec-b718e7abd62b ]
emmc=
for node in /sys/class/block/mmcblk[0-9]*; do
    name=${node##*/}
    case "${name#mmcblk}" in ''|*[!0-9]*) continue ;; esac
    [ -f "$node/device/cid" ] || continue
    [ "$(cat "$node/device/cid")" = 1101004d4d4333324703100a18dd6e00 ] || continue
    case "$(readlink -f "$node")" in *c8000600.mmc*) ;; *) continue ;; esac
    [ -z "$emmc" ] || { echo 'Ambiguous internal eMMC' >&2; exit 1; }
    emmc=/dev/${node##*/}
done
[ -n "$emmc" ]
emmc_name=${emmc##*/}
[ "$(cat "/sys/class/block/$emmc_name/size")" -eq 62521344 ]
boot0=${emmc}boot0
boot1=${emmc}boot1
for boot in "$boot0" "$boot1"; do
    [ "$(cat "/sys/class/block/${boot##*/}/size")" -eq 4096 ]
    [ "$(cat "/sys/class/block/${boot##*/}/force_ro")" -eq 1 ]
done
awk -v dev="$emmc" '$1 ~ ("^" dev) {bad=1} END {exit bad}' /proc/mounts
[ "$(sha256sum "$boot0" | cut -d ' ' -f 1)" = "$expected_old_boot0" ]
[ "$(sha256sum "$boot1" | cut -d ' ' -f 1)" = "$expected_boot1" ]
[ "$(dd if="$emmc" bs=1M count=10 2>/dev/null | sha256sum | cut -d ' ' -f 1)" = "$expected_prefix" ]
printf 'PRECHECK_OK: %s, boot0 only, offset 0, 4096 sectors, SHA256 %s\n' "$boot0" "$expected_image"
if [ "$mode" = --check ]; then
    echo 'No internal writes performed.'
    exit 0
fi
command -v blockdev >/dev/null
readonly_flag=/sys/class/block/${boot0##*/}/force_ro
trap 'echo 1 > "$readonly_flag"' EXIT HUP INT TERM
echo 0 > "$readonly_flag"
dd if="$image" of="$boot0" bs=512 count=4096 conv=fsync
sync
blockdev --flushbufs "$boot0"
[ "$(sha256sum "$boot0" | cut -d ' ' -f 1)" = "$expected_image" ]
echo 1 > "$readonly_flag"
[ "$(sha256sum "$boot1" | cut -d ' ' -f 1)" = "$expected_boot1" ]
[ "$(dd if="$emmc" bs=1M count=10 2>/dev/null | sha256sum | cut -d ' ' -f 1)" = "$expected_prefix" ]
echo 'BOOT0_WRITE_AND_READBACK_OK: boot1 and main prefix unchanged.'
