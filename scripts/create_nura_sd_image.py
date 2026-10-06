#!/usr/bin/env python3
"""Create and fsck an SD image in Docker, without opening any host block disk."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

project = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', default='build/nura-sd-20261006')
parser.add_argument('--lock', default='port/image-inputs.lock.json')
parser.add_argument('--password-file', default='build/image-inputs/login-password')
parser.add_argument('--network-profile', help='Optional private NetworkManager keyfile')
args = parser.parse_args()
out = (project / args.output).resolve()
if not out.is_relative_to(project / 'build'):
    raise SystemExit('Image output must be inside the project build directory')
lock_path = (project / args.lock).resolve()
lock = json.loads(lock_path.read_text())
xorg_module = lock.get('xorg_module', 'build/opentegra-dri3/src/.libs/opentegra_drv.so')
if xorg_module not in lock['files']:
    raise SystemExit('Selected Xorg module must be a locked input')
def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()
for name, expected in lock['files'].items():
    path = (project / name).resolve()
    if not path.is_relative_to(project) or digest(path) != expected:
        raise SystemExit(f'Frozen input missing or changed: {name}')
password = (project / args.password_file).read_text().strip()
if not password or '\n' in password or ':' in password:
    raise SystemExit('Password file must contain one nonempty password without colon')
network_profile = (project / args.network_profile).resolve() if args.network_profile else None
if network_profile and (not network_profile.is_relative_to(project / 'build') or
                        not network_profile.is_file()):
    raise SystemExit('Private network profile must be a file under build/')
out.mkdir(parents=True, exist_ok=True)
root_uuid = str(uuid.UUID((project / 'build/nura-sd-root.uuid').read_text().strip()))
manifest_path = out / 'image-manifest.json'
image = out / 'thinkpad-nura-sd.img'
if image.exists():
    raise SystemExit('Image already exists; keep or move it before regenerating.')
kernel = project / 'build/linux-nura/arch/arm/boot/zImage'
dtb = project / 'build/linux-nura/arch/arm/boot/dts/nvidia/tegra20-lenovo-indigo.dtb'
initrd = project / 'build/nura-sd-test/initramfs.cpio.gz'
for path in (kernel, dtb, initrd, project / 'build/ntrig-spi/ntrig_indigo.ko',
             project / 'build/linux-nura/drivers/reset/reset-gpio.ko',
             project / 'build/input-monitor',
             project / 'build/linux-firmware/brcmfmac4329-sdio.bin',
             project / 'build/linux-firmware/LICENCE.broadcom_bcm43xx'):
    if not path.is_file():
        raise SystemExit(f'Missing boot artifact: {path}')
release = (project / 'build/linux-nura/include/config/kernel.release').read_text().strip()
if release != '7.0.1-nura-indigo-ram':
    raise SystemExit(f'Unexpected kernel release: {release}')

# Run this preparation with container-root so numeric ownership and xattrs survive.
prepare = r'''set -eu
stage="$OUT/rootfs"
test ! -e "$stage"
mkdir "$stage"
tar --numeric-owner --xattrs --acls -xzf /work/build/image-inputs/rootfs.tar.gz -C "$stage"
test -x "$stage/sbin/init"
# pmbootstrap bind-mounts trusted keys while building; restore package backups
# after those mounts disappear so the installed tablet can verify repositories.
mkdir -p "$stage/etc/apk/keys"
cp "$stage/usr/share/apk/keys/"*.pub "$stage/etc/apk/keys/"
# All files were hash checked by the caller. APK also checks trusted signatures,
# resolves against the installed database, and cannot fetch/upgrade online.
apk --root "$stage" --arch armv7 --network=no --no-scripts add $OVERLAY_APKS
rm -f "$stage/usr/bin/qemu-arm-static"
rm -rf "$stage/tmp"/* "$stage/mnt/pmbootstrap"
mkdir -p "$stage/proc" "$stage/sys" "$stage/dev" "$stage/run" "$stage/root"
if [ -d "$stage/etc/skel" ]; then
    cp -a "$stage/etc/skel/." "$stage/home/julian/"
fi
mkdir -p "$stage/home/julian/.config/indigo-tablet" "$stage/etc/xdg/autostart" \
    "$stage/usr/local/bin"
cp /work/port/desktop/rotation-default.json \
    "$stage/home/julian/.config/indigo-tablet/rotation.json"
cp /work/port/desktop/indigo-tablet.desktop "$stage/etc/xdg/autostart/"
install -m 755 /work/port/desktop/indigo-rotate.py "$stage/usr/local/bin/indigo-rotate"
install -m 755 /work/port/desktop/indigo-buttons.sh "$stage/usr/local/bin/indigo-buttons"
install -m 755 /work/port/desktop/indigo-tablet-start.sh "$stage/usr/local/bin/indigo-tablet-start"
install -m 755 /work/port/desktop/setup-indigo-desktop.sh "$stage/usr/local/bin/setup-indigo-desktop"
install -m 755 /work/port/mesa/indigo-gpu-run "$stage/usr/local/bin/indigo-gpu-run"
tar -xzf /work/build/mesa-grate-armv7.tar.gz -C "$stage"
tar -xzf /work/build/mesa-grate-candidate-armv7.tar.gz -C "$stage"
private="$stage/opt/indigo-xorg/xfce"
mkdir -p "$private/lib/xorg/modules/drivers"
install -m 644 "$XORG_MODULE" "$private/lib/xorg/modules/drivers/opentegra_drv.so"
printf 'Section "Module"\n    Load "exa"\nEndSection\n' > "$private/indigo-xorg.conf"
# Require the desktop dependencies in the newly built rootfs before imaging it.
for tool in python3 xrandr xinput xdotool xfconf-query; do
    test -x "$stage/usr/bin/$tool"
done
chown -R 10000:10000 "$stage/home/julian"
test -x "$stage/etc/init.d/chronyd"
mkdir -p "$stage/etc/runlevels/default"
ln -sf /etc/init.d/chronyd "$stage/etc/runlevels/default/chronyd"
mkdir -p "$stage/etc/lightdm/lightdm.conf.d"
cat > "$stage/etc/lightdm/lightdm.conf.d/95-indigo-xorg.conf" <<'EOF'
[Seat:*]
xserver-command=/usr/libexec/Xorg -modulepath /opt/indigo-xorg/xfce/lib/xorg/modules,/usr/lib/xorg/modules -config /opt/indigo-xorg/xfce/indigo-xorg.conf
EOF
cat > "$stage/etc/lightdm/lightdm.conf.d/90-indigo.conf" <<'EOF'
[Seat:*]
autologin-user=julian
autologin-user-timeout=0
autologin-session=xfce
user-session=xfce
EOF
printf 'julian:%s\n' "$LOGIN_PASSWORD" | chpasswd -P "$stage"
if [ -n "$NETWORK_PROFILE" ]; then
    install -m 600 "$NETWORK_PROFILE" "$stage/etc/NetworkManager/system-connections/indigo-wifi.nmconnection"
fi
cat >> "$stage/etc/inittab" <<'EOF'

# Temporary wired root shell for hardware bring-up; no network autologin.
ttyGS0::respawn:/sbin/getty -n -l /bin/sh -L 115200 ttyGS0 vt100
EOF
printf 'UUID=%s / ext4 defaults,noatime 0 1\n' "$ROOT_UUID" > "$stage/etc/fstab"
printf 'evdev\nhid-generic\nusbhid\nreset-gpio\nntrig_indigo\n' >> "$stage/etc/modules"
cp /work/build/linux-firmware/brcmfmac4329-sdio.bin "$stage/lib/firmware/brcm/"
cp /work/build/stock/firmware/brcmfmac4329-sdio.txt "$stage/lib/firmware/brcm/"
mkdir -p "$stage/usr/share/licenses/indigo-wifi"
cp /work/build/linux-firmware/LICENCE.broadcom_bcm43xx "$stage/usr/share/licenses/indigo-wifi/"
cp /work/build/linux-nura/arch/arm/boot/zImage "$stage/boot/vmlinuz-indigo"
cp /work/build/linux-nura/arch/arm/boot/dts/nvidia/tegra20-lenovo-indigo.dtb "$stage/boot/"
cp /work/build/nura-sd-test/initramfs.cpio.gz "$stage/boot/initramfs-indigo"
mkdir -p "$stage/usr/local/sbin"
cp /work/build/ram-test/reboot-into-apx "$stage/usr/local/sbin/"
chmod 755 "$stage/usr/local/sbin/reboot-into-apx"
mkdir -p "$stage/usr/local/bin"
cp /work/build/input-monitor "$stage/usr/local/bin/"
chmod 755 "$stage/usr/local/bin/input-monitor"
mkdir -p "$stage/lib/modules/$KERNEL_RELEASE/kernel/drivers/input" \
    "$stage/lib/modules/$KERNEL_RELEASE/kernel/drivers/hid/usbhid" \
    "$stage/lib/modules/$KERNEL_RELEASE/kernel/drivers/reset" \
    "$stage/lib/modules/$KERNEL_RELEASE/extra"
cp /work/build/linux-nura/drivers/input/evdev.ko \
   "$stage/lib/modules/$KERNEL_RELEASE/kernel/drivers/input/"
cp /work/build/linux-nura/drivers/hid/hid-generic.ko \
   "$stage/lib/modules/$KERNEL_RELEASE/kernel/drivers/hid/"
cp /work/build/linux-nura/drivers/hid/usbhid/usbhid.ko \
   "$stage/lib/modules/$KERNEL_RELEASE/kernel/drivers/hid/usbhid/"
cp /work/build/linux-nura/drivers/reset/reset-gpio.ko \
   "$stage/lib/modules/$KERNEL_RELEASE/kernel/drivers/reset/"
cp /work/build/ntrig-spi/ntrig_indigo.ko "$stage/lib/modules/$KERNEL_RELEASE/extra/"
cp /work/build/linux-nura/modules.builtin /work/build/linux-nura/modules.builtin.modinfo \
   "$stage/lib/modules/$KERNEL_RELEASE/"
printf 'kernel/drivers/input/evdev.ko\nkernel/drivers/hid/hid-generic.ko\nkernel/drivers/hid/usbhid/usbhid.ko\nkernel/drivers/reset/reset-gpio.ko\nextra/ntrig_indigo.ko\n' \
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
truncate -s 4G "$OUT/root.ext4"
mke2fs -t ext4 -F -U "$ROOT_UUID" -L NURA_INDIGO -m 0 \
    -O ^metadata_csum_seed,^64bit -d "$stage" "$OUT/root.ext4"
e2fsck -fn "$OUT/root.ext4"
'''
subprocess.run(['docker', 'run', '--rm', '--network', 'none',
                '-v', f'{project}:/work', '-e', f'ROOT_UUID={root_uuid}',
                '-e', f'KERNEL_RELEASE={release}',
                '-e', f'OUT=/work/{out.relative_to(project)}',
                '-e', 'LOGIN_PASSWORD',
                '-e', f'XORG_MODULE=/work/{xorg_module}',
                '-e', f'NETWORK_PROFILE={"/work/" + str(network_profile.relative_to(project)) if network_profile else ""}',
                '-e', 'OVERLAY_APKS=' + ' '.join('/work/' + p for p in lock['overlay_packages']),
                lock['containers']['thinkpad-pmbootstrap:2026-10-05'], 'sh', '-c', prepare],
               check=True, env=dict(os.environ, LOGIN_PASSWORD=password))
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
manifest = {'root_uuid': root_uuid, 'kernel_release': release,
            'image': str(image.relative_to(project)), 'size': size,
            'sha256': digest(image),
            'boot_artifacts': {str(p.relative_to(project)): digest(p)
                               for p in (kernel, dtb, initrd)},
            'hardware_artifacts': {
                name: digest(project / name) for name in (
                    'build/ntrig-spi/ntrig_indigo.ko',
                    'build/linux-nura/drivers/reset/reset-gpio.ko',
                    'build/linux-firmware/brcmfmac4329-sdio.bin',
                    'build/stock/firmware/brcmfmac4329-sdio.txt',
                    'build/linux-firmware/LICENCE.broadcom_bcm43xx')},
            'sources': json.loads((project / 'sources.lock.json').read_text()),
            'input_lock': str(lock_path.relative_to(project)),
            'input_lock_sha256': digest(lock_path),
            'assembler_container': lock['containers']['thinkpad-pmbootstrap:2026-10-05'],
            'graphics': {'xorg': 'private fixed opentegra; stock module retained',
                         'xorg_module_source': xorg_module,
                         'mesa': 'distribution default; private builds selected per process'},
            'private_network_profile_included': network_profile is not None,
            'verified': 'All frozen input hashes, offline signed APK installation, e2fsck -fn before disk-image assembly',
            'installation': 'external SD; tablet bootloader remains on Android'}
manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
(out / 'SHA256SUMS').write_text(f'{manifest["sha256"]}  {image.name}\n')
print(f'Created and checked {image}: {size} bytes, SHA256 {manifest["sha256"]}')
