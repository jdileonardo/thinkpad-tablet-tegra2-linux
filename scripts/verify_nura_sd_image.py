#!/usr/bin/env python3
"""Read-only verification of the assembled SD image and selected runtime files."""
import argparse
import ctypes
import ctypes.util
import hashlib
import json
import re
import struct
import subprocess
import tarfile
from pathlib import Path


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    if not __debug__:
        raise SystemExit('Verification must run without Python optimization')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', default='build/nura-sd-20261006/image-manifest.json')
    parser.add_argument('--password-file', default='build/image-inputs/login-password')
    parser.add_argument('--network-profile', default='build/image-inputs/indigo-wifi.nmconnection')
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    manifest_path = (project / args.manifest).resolve()
    manifest = json.loads(manifest_path.read_text())
    image = project / manifest['image']
    filesystem = manifest_path.parent / 'root.ext4'
    lock = json.loads((project / manifest['input_lock']).read_text())
    assert digest(project / manifest['input_lock']) == manifest['input_lock_sha256']
    assert image.stat().st_size == manifest['size']
    assert digest(image) == manifest['sha256']
    with image.open('rb') as stream:
        header = stream.read(512)
        assert header[510:512] == b'\x55\xaa'
        boot, _, kind, _, start, sectors = struct.unpack('<B3sB3sII', header[446:462])
        assert (boot, kind, start, sectors) == (128, 131, 2048, filesystem.stat().st_size // 512)
        assert header[462:510] == bytes(48)
        stream.seek(start * 512)
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == digest(filesystem)
    def read(name):
        result = subprocess.run(['debugfs', '-R', f'cat {name}', str(filesystem)],
                                capture_output=True, check=True)
        if b'File not found' in result.stderr:
            raise RuntimeError(f'Missing image file: {name}')
        return result.stdout
    checked = {}
    targets = {
        '/boot/vmlinuz-indigo': 'build/linux-nura/arch/arm/boot/zImage',
        '/boot/initramfs-indigo': 'build/nura-sd-test/initramfs.cpio.gz',
        '/boot/tegra20-lenovo-indigo.dtb': 'build/linux-nura/arch/arm/boot/dts/nvidia/tegra20-lenovo-indigo.dtb',
        '/opt/indigo-xorg/xfce/lib/xorg/modules/drivers/opentegra_drv.so': manifest['graphics'].get(
            'xorg_module_source', 'build/opentegra-dri3/src/.libs/opentegra_drv.so'),
        '/usr/local/bin/indigo-gpu-run': 'port/mesa/indigo-gpu-run',
        '/usr/local/bin/indigo-rotate': 'port/desktop/indigo-rotate.py',
        '/usr/local/bin/indigo-buttons': 'port/desktop/indigo-buttons.sh',
        '/usr/local/bin/indigo-tablet-start': 'port/desktop/indigo-tablet-start.sh',
        '/usr/local/bin/setup-indigo-desktop': 'port/desktop/setup-indigo-desktop.sh',
        '/etc/xdg/autostart/indigo-tablet.desktop': 'port/desktop/indigo-tablet.desktop',
        '/home/julian/.config/indigo-tablet/rotation.json': 'port/desktop/rotation-default.json',
        '/usr/lib/firmware/brcm/brcmfmac4329-sdio.bin': 'build/linux-firmware/brcmfmac4329-sdio.bin',
        '/usr/lib/firmware/brcm/brcmfmac4329-sdio.txt': 'build/stock/firmware/brcmfmac4329-sdio.txt',
    }
    modules = {'extra/ntrig_indigo.ko': manifest.get('ntrig_module_source', 'build/ntrig-spi/ntrig_indigo.ko'),
               'kernel/drivers/input/evdev.ko': 'build/linux-nura/drivers/input/evdev.ko',
               'kernel/drivers/reset/reset-gpio.ko': 'build/linux-nura/drivers/reset/reset-gpio.ko',
               'kernel/drivers/hid/hid-generic.ko': 'build/linux-nura/drivers/hid/hid-generic.ko',
               'kernel/drivers/hid/usbhid/usbhid.ko': 'build/linux-nura/drivers/hid/usbhid/usbhid.ko'}
    targets.update({f'/usr/lib/modules/{manifest["kernel_release"]}/{name}': source
                    for name, source in modules.items()})
    for target, source in targets.items():
        actual = hashlib.sha256(read(target)).hexdigest()
        assert actual == lock['files'][source], target
        checked[target] = actual
    for archive in ('build/mesa-grate-armv7.tar.gz', 'build/mesa-grate-candidate-armv7.tar.gz'):
        with tarfile.open(project / archive) as source:
            members = [member for member in source if member.isfile() and
                       '/lib/' in member.name and '.so' in member.name]
            for member in members:
                if not member.isfile():
                    continue
                target = '/' + member.name.removeprefix('./')
                expected = hashlib.sha256(source.extractfile(member).read()).hexdigest()
                actual = hashlib.sha256(read(target)).hexdigest()
                assert actual == expected, target
                checked[target] = actual
    stock = read('/usr/lib/xorg/modules/drivers/opentegra_drv.so')
    assert stock and hashlib.sha256(stock).hexdigest() != checked[
        '/opt/indigo-xorg/xfce/lib/xorg/modules/drivers/opentegra_drv.so']
    from install_indigo_xorg import SETTINGS
    assert read('/etc/lightdm/lightdm.conf.d/95-indigo-xorg.conf').decode() == SETTINGS
    assert b'autologin-user=julian' in read('/etc/lightdm/lightdm.conf.d/90-indigo.conf')
    assert f'UUID={manifest["root_uuid"]} / ext4'.encode() in read('/etc/fstab')
    assert b'ttyGS0::respawn:' in read('/etc/inittab')
    passwd = next(line.split(':') for line in read('/etc/passwd').decode().splitlines()
                  if line.startswith('julian:'))
    assert passwd[2:4] == ['10000', '10000']
    shadow = next(line.split(':')[1] for line in read('/etc/shadow').decode().splitlines()
                  if line.startswith('julian:'))
    crypt = ctypes.CDLL(ctypes.util.find_library('crypt')).crypt
    crypt.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    crypt.restype = ctypes.c_char_p
    password = (project / args.password_file).read_text().strip().encode()
    assert crypt(password, shadow.encode()).decode() == shadow, 'Password does not match'
    if manifest['private_network_profile_included']:
        target = '/etc/NetworkManager/system-connections/indigo-wifi.nmconnection'
        assert read(target) == (project / args.network_profile).read_bytes()
        stat = subprocess.check_output(['debugfs', '-R', f'stat {target}', str(filesystem)],
                                       stderr=subprocess.DEVNULL, text=True)
        assert re.search(r'Mode:\s+0600', stat) and re.search(r'User:\s+0\s+Group:\s+0', stat)
    report = {'image_sha256': manifest['sha256'], 'partition_matches_checked_ext4': True,
              'file_sha256': checked, 'autologin_and_password_verified': True,
              'private_wifi_profile_and_permissions_verified': manifest['private_network_profile_included'],
              'stock_xorg_retained': True, 'physical_boot_verified': False,
              'scope': 'Host readback of image contents; not a hardware boot or graphics test'}
    path = manifest_path.parent / 'image-content-verification.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Image partition, {len(checked)} files, autologin and requested password verified')


if __name__ == '__main__':
    main()
