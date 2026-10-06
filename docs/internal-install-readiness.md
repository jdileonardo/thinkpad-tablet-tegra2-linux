# Internal Linux installation readiness

Read-only checkpoint, 2026-10-06. No internal writes were performed.

The user wants a clean Linux installation and does not need Android, cache or
userdata preserved. Missing cache/userdata backups are therefore not an
installation prerequisite. The current XFCE SD image has passed two APX boots,
physical touch/rotation/button checks, automatic Wi-Fi connection, and graphics
buffer checks; see [the image checkpoint](xfce-image.md).

The OS is ready for the next installation stage. The current boot artifacts are
not yet a flashable, host-independent installation: U-Boot assumes the kernel,
initramfs and DTB are already in RAM, and the bootstrap accepts only the external
SD controller and UUID. Flashing those artifacts unchanged would not provide
cold boot into Linux.

## Recovery and backups

All 13 files in `backups/MP0GKR7-20261005T160450Z/` passed their saved SHA256 and
length checks. Both live 2 MiB eMMC boot regions and the first 10 MiB of the main
area still match their backups. The saved BCT includes this board's SDRAM/MMC
parameters and has already been used for repeated successful APX RAM boots.
This is useful board and boot recovery material; a full stock restore has not
been tested. Proprietary backup binaries remain outside Git.

The legacy Android tail backup passes its own saved hash, but a live read at its
recorded address differs. The cause is unestablished. A fresh 1 MiB physical-end
backup was captured and transfer-hash verified. Keep both captures and their
different coordinates; do not treat the legacy tail as a verified current-end
backup.

Tegra's recovery mode runs in ROM, with hardware force-recovery independent of
the installed bootloader. Software boot failures should therefore remain
recoverable through APX on this already-tested unit. Hardware failure can still
prevent recovery. See NVIDIA's [boot-flow documentation](https://download.nvidia.com/tegra-public-appnotes/tegra-boot-flow.html).

## Verified storage identity and addressing

| Item | Read-only observation |
| --- | --- |
| Tablet serial | MP0GKR7 |
| eMMC CID | `1101004d4d4333324703100a18dd6e00` |
| Linux internal device at audit | `/dev/mmcblk1`, controller `c8000600.mmc` |
| Main area | 62,521,344 sectors of 512 bytes, 32,010,928,128 bytes |
| Hardware boot areas | Two areas, 2,097,152 bytes each; both `force_ro=1` |
| EXT_CSD | Revision 5, boot size multiplier 16, sector count matches Linux |
| EXT_CSD boot configuration | PARTITION_CONFIG=0, BOOT_BUS_WIDTH=0 after Linux initialization |
| Android-reported main capacity | 62,513,152 sectors; 8,192 fewer than Linux |

The capacity difference equals the combined boot-area size, but the precise
reason for Android's report has not been established. NVIDIA's proprietary
layout linearizes boot0, boot1 and the main area. Linux exposes them separately;
raw NVIDIA partition coordinates require the appropriate boot-area offset.
See [NVIDIA's flashing guide](https://download.nvidia.com/tegra-public-appnotes/flashing-tools.html)
and `sources/linux-nura/block/partitions/tegra.c`.

The current kernel has the Tegra partition parser enabled, but its command line
omits `tegraboot=sdmmc`; the parser returns without exposing legacy partitions.
That is not evidence that the eMMC is empty. A clean Linux layout must be
specified using freshly verified device identity and physical coordinates.
The EXT_CSD capture is an initialized-Linux snapshot, not a confirmed original
power-on configuration or an instruction to restore those bytes.

## Remaining implementation

1. Build a separate storage-loading U-Boot profile. Test it through APX while
   reading kernel, initramfs and DTB from the working SD card. Check its MMC
   numbering: U-Boot's internal `mmc0` and external `mmc1` differ from Linux's
   current numbering.
2. Generate the persistent boot image with the saved board BCT parameters,
   updated bootloader length, location and hash. Inspect its bounds and define
   the target boot region and any required MMC boot configuration changes.
   The current combined RAM payload is much larger than a hardware boot area;
   it is not a boot-area flash image.
3. Prepare an internal-root profile and a clean eMMC user-area image. Reuse the
   validated root filesystem contents with an explicit internal controller/UUID
   selection; do not use the SD whole-disk image unchanged as an installation
   recipe.
4. Package the exact bounded writes, readback verification and recovery steps.
   Retain the known-good APX payload, saved BCT and working SD root. A staged
   first installation can boot the existing SD root from persistent U-Boot,
   followed by the internal root deployment.
5. After installation, check cold power-on without the host, XFCE autologin,
   touch, rotation, buttons and Wi-Fi on dock power.

No additional 30-minute observation is required by the user. Long-duration
reliability, battery reporting, pen testing and calendar/Spotify integrations
remain separate follow-ups.

The [readiness record](evidence/internal-install-20261006/readiness.json),
[backup audit](evidence/internal-install-20261006/backup-audit.json),
[live boot-region check](evidence/internal-install-20261006/live-boot-regions.txt),
[EXT_CSD capture](evidence/internal-install-20261006/live-ext-csd.txt), and
[physical-tail capture](evidence/internal-install-20261006/live-physical-tail.txt)
record the evidence for this checkpoint.
