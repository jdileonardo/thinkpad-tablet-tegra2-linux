# Internal installation

The user authorized flashing boot storage and a clean internal Linux image on
2026-10-06, with cache/userdata and Android preservation not required.

See [build, copy and flash instructions](build-copy-flash.md) for the commands,
preserved prerequisites and distinction between the tested first installation
and a reusable reflash tool.

The [installation plan](evidence/extlinux-install-20261006/installation-plan.json)
records the two stages: install the 2 MiB hardware boot0 image and verify a normal
ROM boot into the working SD system, then install the prepared internal root and
verify boot from eMMC. The hardware boot1 area is retained. Physical SD removal
and a cold power-on must be checked when the user returns.

U-Boot now reads replaceable `/boot/extlinux/extlinux.conf`, trying SD then
internal eMMC. Two physical APX boots used the same U-Boot binary with different
configurations and kernel pathnames. Both also used the new BCT, whose board
parameters were byte-preserved and whose AES-CMAC was independently checked.

Host artifacts are `build/internal-boot-20261006/boot-region-padded.img` and
`build/nura-internal-20261006/internal-user-area.img`. The internal image has a
distinct filesystem UUID and MBR identity, selects controller `c8000600.mmc`,
and passed filesystem/content checks. Private images remain outside Git.

The [boot0 installer](../port/internal/boot0-install.sh) defaults to a read-only
preflight and passed on the actual device. Applying it verifies identity,
existing backups, exact target size, image hash and the SD recovery root before
writing. It restores boot write protection and checks readback and untouched
boot1/main-prefix hashes afterward. The original BCT, APX RAM payload, SD root
and original hardware boot-region backups are retained for recovery.

## Installed bootloader

The boot0 write and full 2 MiB readback passed. Boot1 and the original first
10 MiB of the main area remained unchanged. Both hardware boot areas are
write-protected again. A normal ROM restart then loaded XFCE from SD without
an APX download; Wi-Fi reconnected automatically. See the
[write/readback log](evidence/extlinux-install-20261006/boot0-flash-readback.txt)
and [ROM boot identity](evidence/extlinux-install-20261006/first-rom-boot-identity.txt).
Linux changed its MMC numbering on that restart, so the main-area installer
continues to discover internal storage by controller, CID and capacity.

The [main-area installer](../port/internal/user-area-install.sh) validates the
source image and original main prefix, writes the bounded 4,097 MiB image,
checks its entire readback, then expands the partition and ext4 filesystem to
the internal capacity. Both hardware boot areas remain protected and their
hashes are checked again. Internal installation results follow below.


## Internal Linux installation result

The main-area image was written and its complete 4,296,015,872-byte readback
matched the source SHA256. The partition was expanded to 62,519,296 sectors;
ext4 was expanded to 7,814,912 blocks of 4 KiB. Read-only filesystem checks
passed before and after expansion. Both boot-region hashes stayed unchanged.
See the [installation log](evidence/extlinux-install-20261006/internal-install-log.txt)
and [read-only installed-root inspection](evidence/extlinux-install-20261006/installed-root-inspection.txt).

The SD configuration was renamed to `/boot/extlinux/extlinux.conf.sd-recovery`.
A normal ROM restart, with no APX download, loaded the internal extlinux entry
and started XFCE with autologin. The root is `/dev/mmcblk0p1` on controller
`c8000600.mmc`, UUID `a1b59fdc-49f7-46bb-b099-4c6012334c07`. Device numbering
is an observation of this boot, not a target identifier for future writes.
The filesystem reports 29.3 GiB total and 28.2 GiB available.

The [boot check](evidence/extlinux-install-20261006/internal-rom-boot-startup.txt)
and [runtime check](evidence/extlinux-install-20261006/internal-rom-boot-runtime.txt)
confirm internal root, automatic Wi-Fi reconnection, three successful network
pings, N-Trig registration, all 34 selected runtime hashes and 770 packages.
Boot0 and boot1 remain protected; boot1 retains its original content. The SD
has no mounted filesystem on this internal boot and remains available for APX
recovery. Normal kernel or userspace iteration does not require reflashing
U-Boot; see the updated [development workflow](development-workflow.md).

The [desktop ready check](evidence/extlinux-install-20261006/internal-desktop-ready.txt)
confirms rotation autostart, synchronized touch coordinates, registered touch,
pen and GPIO button inputs, and the selected opentegra Xorg driver. The
[final state](evidence/extlinux-install-20261006/internal-final-state.txt) has
only the internal MMC root mounted, approximately 713 MiB of available RAM
and no used swap. The SD card can be removed from this running system.

The tablet was left running XFCE from internal storage. The user was away,
so physical SD removal and a cold power-on are still untested, as is a fresh
physical touch/rotation/button check on this internal installation. Their
previous SD-image validation remains recorded. No additional 30-minute
observation was run. The internal-root APX payload was built and recorded,
but its hardware test remains separate from the proven APX/SD recovery path.
