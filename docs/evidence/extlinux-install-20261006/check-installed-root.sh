#!/bin/sh
set -eu
trap 'umount /mnt/indigo-internal-inspect 2>/dev/null || true' EXIT
grep -qx INTERNAL_INSTALL_AND_EXPANSION_OK /run/internal-install.log
grep -qx INTERNAL_INSTALL_EXIT=0 /run/internal-install.log
grep -qx INSTALL_RUNNER_EXIT=0 /run/internal-install.log
emmc=
for node in /sys/class/block/mmcblk[0-9]*; do
 name=${node##*/}; case "${name#mmcblk}" in ''|*[!0-9]*) continue ;; esac
 [ -f "$node/device/cid" ] || continue
 [ "$(cat "$node/device/cid")" = 1101004d4d4333324703100a18dd6e00 ] || continue
 case "$(readlink -f "$node")" in *c8000600.mmc*) ;; *) continue ;; esac
 [ -z "$emmc" ] || exit 1
 emmc=/dev/$name
done
[ -n "$emmc" ]
[ "$(/bin/busybox blkid "${emmc}p1" | sed -n 's/.* UUID="\([^"]*\)".*/\1/p')" = a1b59fdc-49f7-46bb-b099-4c6012334c07 ]
[ "$(cat /sys/class/block/${emmc##*/}p1/size)" -eq 62519296 ]
mkdir -p /mnt/indigo-internal-inspect
mount -t ext4 -o ro "${emmc}p1" /mnt/indigo-internal-inspect
cd /mnt/indigo-internal-inspect
[ "$(sha256sum etc/fstab | cut -d ' ' -f 1)" = b9362e9a34ab2dc24e5bff06e61653881fed73e50540b0663be467a7d5ce6a1b ]
[ "$(sha256sum boot/extlinux/extlinux.conf | cut -d ' ' -f 1)" = 75fb3a407a8f0c571e442d16c98f78dda1dbbf147feb2e2c265650b0e1dcc55f ]
[ "$(sha256sum boot/initramfs-indigo | cut -d ' ' -f 1)" = 095877922ca4aec038af2e5fd52db12d0642a0fa8b03cf8844613c4e547d9fc2 ]
[ "$(sha256sum boot/vmlinuz-indigo | cut -d ' ' -f 1)" = 5c1afb5c526506209b86a69424ffef25b65b2b9640490e1c3b46ea0b91fea9ff ]
[ "$(sha256sum boot/tegra20-lenovo-indigo.dtb | cut -d ' ' -f 1)" = b9de2d486774d32b8d1a87c2a36374a07c5c3ceb327d9ceaf3ade8abdc9be73b ]
[ -x sbin/init ]
cat etc/fstab boot/extlinux/extlinux.conf
df -h .
cd /
umount /mnt/indigo-internal-inspect
trap - EXIT
echo INSTALLED_INTERNAL_ROOT_INSPECTION_OK
