#!/usr/bin/env python3
"""Create and fsck an SD image in Docker, without opening any host block disk."""
import hashlib
import json
import shutil
import subprocess
import uuid
from pathlib import Path

project = Path(__file__).resolve().parents[1]
out = project / 'build/nura-sd'
out.mkdir(parents=True, exist_ok=True)
root_uuid = str(uuid.UUID((project / 'build/nura-sd-root.uuid').read_text().strip()))
manifest_path = out / 'image-manifest.json'
image = out / 'thinkpad-nura-sd.img'
if image.exists():
    raise SystemExit('Image already exists; keep or move it before regenerating.')
kernel = project / 'build/linux-nura/arch/arm/boot/zImage'
dtb = project / 'build/linux-nura/arch/arm/boot/dts/nvidia/tegra20-lenovo-indigo.dtb'
initrd = project / 'build/nura-sd-test/initramfs.cpio.gz'
for path in (kernel, dtb, initrd):
    if not path.is_file():
        raise SystemExit(f'Missing boot artifact: {path}')
release = (project / 'build/linux-nura/include/config/kernel.release').read_text().strip()
if release != '7.0.1-nura-indigo-ram':
    raise SystemExit(f'Unexpected kernel release: {release}')

# Run this preparation with container-root so numeric ownership and xattrs survive.
prepare = r'''set -eu
source=/work/build/pmbootstrap/chroot_rootfs_nvidia-tegra-armv7
stage=/work/build/nura-sd/rootfs
test -x "$source/sbin/init"
test ! -e "$stage"
cp -a "$source" "$stage"
rm -f "$stage/usr/bin/qemu-arm-static"
rm -rf "$stage/tmp"/* "$stage/mnt/pmbootstrap"
mkdir -p "$stage/proc" "$stage/sys" "$stage/dev" "$stage/run" "$stage/root"
if [ -d "$stage/etc/skel" ]; then
    cp -a "$stage/etc/skel/." "$stage/home/julian/"
fi
chown -R 10000:10000 "$stage/home/julian"
mkdir -p "$stage/etc/lightdm/lightdm.conf.d"
cat > "$stage/etc/lightdm/lightdm.conf.d/90-indigo.conf" <<'EOF'
[Seat:*]
autologin-user=julian
autologin-user-timeout=0
autologin-session=xfce
user-session=xfce
EOF
cat >> "$stage/etc/inittab" <<'EOF'

# Temporary wired root shell for hardware bring-up; no network autologin.
ttyGS0::respawn:/sbin/getty -n -l /bin/sh -L 115200 ttyGS0 vt100
EOF
printf 'UUID=%s / ext4 defaults,noatime 0 1\n' "$ROOT_UUID" > "$stage/etc/fstab"
printf 'evdev\nhid-generic\nusbhid\n' >> "$stage/etc/modules"
cp /work/build/stock/firmware/brcmfmac4329-sdio.bin "$stage/lib/firmware/brcm/"
cp /work/build/stock/firmware/brcmfmac4329-sdio.txt "$stage/lib/firmware/brcm/"
cp /work/build/linux-nura/arch/arm/boot/zImage "$stage/boot/vmlinuz-indigo"
cp /work/build/linux-nura/arch/arm/boot/dts/nvidia/tegra20-lenovo-indigo.dtb "$stage/boot/"
cp /work/build/nura-sd-test/initramfs.cpio.gz "$stage/boot/initramfs-indigo"
mkdir -p "$stage/usr/local/sbin"
cp /work/build/ram-test/reboot-into-apx "$stage/usr/local/sbin/"
chmod 755 "$stage/usr/local/sbin/reboot-into-apx"
mkdir -p "$stage/lib/modules/$KERNEL_RELEASE/kernel/drivers/input" \
    "$stage/lib/modules/$KERNEL_RELEASE/kernel/drivers/hid/usbhid"
cp /work/build/linux-nura/drivers/input/evdev.ko \
   "$stage/lib/modules/$KERNEL_RELEASE/kernel/drivers/input/"
cp /work/build/linux-nura/drivers/hid/hid-generic.ko \
   "$stage/lib/modules/$KERNEL_RELEASE/kernel/drivers/hid/"
cp /work/build/linux-nura/drivers/hid/usbhid/usbhid.ko \
   "$stage/lib/modules/$KERNEL_RELEASE/kernel/drivers/hid/usbhid/"
cp /work/build/linux-nura/modules.builtin /work/build/linux-nura/modules.builtin.modinfo \
   "$stage/lib/modules/$KERNEL_RELEASE/"
printf 'kernel/drivers/input/evdev.ko\nkernel/drivers/hid/hid-generic.ko\nkernel/drivers/hid/usbhid/usbhid.ko\n' \
    > "$stage/lib/modules/$KERNEL_RELEASE/modules.order"
depmod -b "$stage" "$KERNEL_RELEASE"
mkdir -p "$stage/boot/extlinux"
cat > "$stage/boot/extlinux/extlinux.conf" <<'EOF'
DEFAULT indigo
TIMEOUT 10
LABEL indigo
  LINUX /boot/vmlinuz-indigo
  INITRD /boot/initramfs-indigo
  FDT /boot/tegra20-lenovo-indigo.dtb
  APPEND console=tty0 console=ttyS0,115200 panic=0 rdinit=/init
EOF
truncate -s 4G /work/build/nura-sd/root.ext4
mke2fs -t ext4 -F -U "$ROOT_UUID" -L NURA_INDIGO -m 0 \
    -O ^metadata_csum_seed,^64bit -d "$stage" /work/build/nura-sd/root.ext4
e2fsck -fn /work/build/nura-sd/root.ext4
'''
subprocess.run(['docker', 'run', '--rm', '--network', 'none',
                '-v', f'{project}:/work', '-e', f'ROOT_UUID={root_uuid}',
                '-e', f'KERNEL_RELEASE={release}',
                'thinkpad-pmbootstrap:2026-10-05', 'sh', '-c', prepare], check=True)
offset = 1024 * 1024
root_image = out / 'root.ext4'
size = offset + root_image.stat().st_size
with image.open('wb') as target:
    target.truncate(size)
    target.seek(offset)
    with root_image.open('rb') as source:
        shutil.copyfileobj(source, target, 8 * 1024 * 1024)
partition_table = (f'label: dos\nunit: sectors\n\n'
                   f'start=2048, size={root_image.stat().st_size // 512}, type=83, bootable\n')
subprocess.run(['sfdisk', str(image)], input=partition_table, text=True, check=True)
def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()
manifest = {'root_uuid': root_uuid, 'kernel_release': release,
            'image': str(image.relative_to(project)), 'size': size,
            'sha256': digest(image),
            'boot_artifacts': {str(p.relative_to(project)): digest(p)
                               for p in (kernel, dtb, initrd)},
            'sources': json.loads((project / 'sources.lock.json').read_text()),
            'verified': 'e2fsck -fn before disk-image assembly',
            'installation': 'external SD; tablet bootloader remains on Android'}
manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
(out / 'SHA256SUMS').write_text(f'{manifest["sha256"]}  {image.name}\n')
print(f'Created and checked {image}: {size} bytes, SHA256 {manifest["sha256"]}')
