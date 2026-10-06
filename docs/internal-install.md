# Internal installation

The user authorized flashing boot storage and a clean internal Linux image on
2026-10-06, with cache/userdata and Android preservation not required.

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

Installation results and any limits will be recorded below as each stage runs.
