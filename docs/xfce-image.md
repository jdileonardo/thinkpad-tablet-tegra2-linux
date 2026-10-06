# XFCE SD image checkpoint, 2026-10-06

The new image is assembled from the cached distribution root filesystem and
verified build artifacts, rather than from the live tablet filesystem.
It uses the fixed private opentegra Xorg driver for XFCE, retains the distribution
driver for rollback, and includes both private Mesa prefixes with the existing
per-process wrapper. Distribution Mesa remains the default for applications.
The selected driver includes both the scanout-reference fix and the
[large-pixmap allocation fallback](graphics-oversize-fix.md).

The image includes the kernel, N-Trig/input modules, Wi-Fi firmware, rotation
and button helpers, and the previously requested autologin/password settings.
The rootfs lacked `xinput` and `xdotool`; two signed, versioned APK files are
installed offline without upgrading its existing libraries. The installed
package count becomes 770, from a frozen baseline of 768.

## Artifact and checks

Image: `build/nura-sd-20261006-cmafix/thinkpad-nura-sd.img`, 4,296,015,872 bytes.

SHA256:

```text
d762aee01165e5342add77438142931cc4c6451640c0839bcdc76ff18129a075
```

The [image manifest](evidence/image-20261006/image-manifest.json) records boot
hashes and the frozen input lock. The [content verification](evidence/image-20261006/image-content-verification.json)
checks the assembled MBR and confirms that its complete partition matches the
checked ext4 filesystem. It verifies boot/firmware/module/desktop files,
private Mesa shared libraries, the selected Xorg driver and retained stock
driver, autologin, the requested password, and private Wi-Fi keyfile permissions.
`e2fsck -fn` passed before assembly.

The [ARM runtime check](evidence/image-20261006/arm-chroot-check.log) runs GTK
imports, Xorg version reporting and input-tool dependency resolution with
static QEMU inside the staged root. It verifies userspace loading, not GPU
operation or tablet boot. The reported host kernel in that log is QEMU's host
system and is not the tablet kernel. It used the preceding image's identical
distribution rootfs and input packages; the corrected private DDX was then
tested directly on the tablet.

This local image includes the active Wi-Fi profile. That profile and the
password input are ignored files under `build/image-inputs/`, absent from Git
and the portable frozen-input export. A distributable image should be rebuilt
without `--network-profile` and with its intended account configuration.

## Frozen inputs and rebuild

[The input lock](../port/image-inputs.lock.json) records SHA256 values for 64
files, including the rootfs/SDK snapshots, package inventories, boot artifacts,
graphics archives and port patches/configuration. It records full immutable
IDs for the pmbootstrap, kernel, Mesa and Xorg builder containers.
The [rootfs inventory](evidence/image-20261006/rootfs-packages.json) and
[SDK inventory](evidence/image-20261006/sdk-packages.json) expose exact installed
package versions, architectures and package checksums.

```sh
python3 scripts/create_nura_sd_image.py --output build/nura-sd-next \
  --password-file build/image-inputs/login-password
python3 scripts/verify_nura_sd_image.py \
  --manifest build/nura-sd-next/image-manifest.json
```

The password file must already exist. Add `--network-profile` only when a
private NetworkManager keyfile is wanted. The builder verifies every locked
input, uses the locked container ID with Docker networking disabled, and refuses
to replace an existing image or rootfs staging directory.

`scripts/export_image_inputs.py` exports `build/image-inputs-cmafix/frozen-inputs.tar`
and `containers.tar.gz`, with SHA256 values in `export-manifest.json`. The first
contains exactly the dated lock and its 64 named inputs; it excludes the local
password input and Wi-Fi profile. Preserve these archives alongside the Git
repository. Restore at the project root and run `docker load` before rebuilding.
The locked container IDs work even if restored images have no tag aliases.
The dated lock is `port/image-inputs-oversize.lock.json`; the main input lock
contains the same data and is the default for rebuilding. The preceding
candidate image and its original input archives are preserved separately.

This freezes binary inputs for offline image assembly. It does not claim
bit-identical ext4 images: filesystem creation timestamps, MBR identifier,
password salt and optional private configuration can differ. Rebuilding every
component from source is separate from restoring these binary inputs.

The [clean DDX source rebuild comparison](evidence/image-20261006/source-rebuild-comparison.json)
records a successful build in `build/opentegra-frozen-check` with the frozen
SDK/container. All ELF sections match the preceding scanout-only driver except the build ID
and 216 bytes of embedded Tegra114 shader data. Tegra20 shader data is unchanged.
The reason for the Tegra114 differences has not been established; the rebuilt
binary was not deployed. The release image retains the hardware-tested binary.

Kernel/N-Trig builders use the locked container when the lock exists. Mesa
and Xorg builders additionally verify the complete SDK against its frozen
archive and skip online package installation. To restore the SDK, extract
`sdk.tar.gz` into an empty `build/mesa-sysroot` with numeric ownership retained.
`INDIGO_REFRESH_BUILD_DEPS=1` explicitly selects the older online dependency
refresh path for Mesa/Xorg; it does not update the release lock. Review and
freeze a new release before adopting changed inputs.

## Card write and remaining hardware checks

The writer now accepts the candidate manifest:

```sh
python3 scripts/write_nura_sd.py --manifest build/nura-sd-20261006-cmafix/image-manifest.json \
  --device DEVICE --expected-serial SERIAL --expected-size BYTES
```

Identify those values freshly after moving the card to the computer. Existing
guards require the expected removable whole USB disk, matching reader identity
and capacity, and no mounted partitions. The writer verifies image SHA256
before erasing, verifies all written bytes, expands the filesystem, checks it,
and records evidence beside the selected image manifest.

Fresh-image boot, repeated APX boots, physical touch/rotation/buttons and
longer application operation remain required. APX RAM boot and the external-SD
root UUID/controller requirements are unchanged; this image does not install
a persistent bootloader or write internal eMMC.
