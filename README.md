# Nura Linux on the Lenovo ThinkPad Tablet (2011, Tegra 2)

A port of [Nura](https://nura.eco/) Linux (libre-tegra kernel, grate GPU
driver, XFCE) to the original 2011 Lenovo ThinkPad Tablet: NVIDIA Tegra20,
board codename "Indigo". It does not cover later Lenovo Tab products.

Working: boot from SD over APX, persistent U-Boot, installation to the internal
eMMC, XFCE with GPU acceleration, N-Trig touch and pen, rotation, Wi-Fi and CPU
frequency scaling.

This README covers three steps:

1. [Put the tablet into APX (NVIDIA recovery) mode](#1-enter-apx-mode)
2. [Start Nura from an SD card](#2-start-nura-from-an-sd-card)
3. [Install Nura to the internal eMMC](#3-install-to-internal-emmc)

> **Warning:** these steps were developed on one unit. The installers check
> that unit's eMMC identity and image hashes, and they refuse anything else.
> Back up your tablet before writing anything.

## 0. Back up first

From Android, with ADB, save the partitions and the board's boot
configuration table (BCT). The BCT is specific to your board. Never use one
from another unit. See [ASSESSMENT.md](ASSESSMENT.md) and
[docs/internal-install-readiness.md](docs/internal-install-readiness.md).
`scripts/backup_tablet.py` is the backup tool used here.

## 1. Enter APX mode

APX is the Tegra boot ROM's USB recovery mode. In this mode the host can load
a bootloader straight into RAM, without changing anything stored on the
tablet.

- **From a powered-off tablet:** unplug USB. Hold the **rotation lock**
  button, then press **Power** for about 2 seconds. The screen stays black.
  Then connect the micro-USB cable to the host. (Source: the community
  [TPT1838 notes](https://github.com/caesarhao/TPT1838); not yet re-checked on
  this unit.)
- **Not APX:** Volume Up + Power starts Android recovery instead.
- **Leaving APX:** hold Power for about 6 seconds.
- **From a running Linux system:** run `reboot-into-apx` as root. The SD image
  installs it at `/usr/local/sbin/reboot-into-apx`.

Then check that the host sees the recovery device:

```sh
lsusb | grep 0955:7820     # NVIDIA APX
```

Sometimes a restart lands in Android instead. Check the USB ID before every
download.

## 2. Start Nura from an SD card

Build and verify the SD image, then write it to a card. The writer erases the
disk you select, so check the device freshly with `lsblk` first:

```sh
python3 scripts/create_nura_sd_image.py --lock port/image-inputs.lock.json \
  --output build/nura-sd-next --password-file build/image-inputs/login-password
python3 scripts/verify_nura_sd_image.py --manifest build/nura-sd-next/image-manifest.json
python3 scripts/write_nura_sd.py --manifest build/nura-sd-next/image-manifest.json \
  --device /dev/ACTUAL_WHOLE_DISK --expected-serial READER_SERIAL --expected-size CARD_BYTES
```

Insert the card, put the tablet in APX mode, and load U-Boot, the kernel and
the initramfs into RAM:

```sh
bash scripts/tegrarcm.sh --usb-timeout=5000 \
  --bct=/work/backups/<backup>/active.bct \
  --bootloader=/work/build/nura-sd-test/thinkpad-ram-payload.bin \
  --loadaddr=0x108000
```

The tablet then boots Nura from the SD card. A USB serial console (`ttyGS0`) is
available through `scripts/ram_console.py`. The full build recipe is in
[PORTING.md](PORTING.md#rebuild-the-nura-sd-boot) and
[docs/build-copy-flash.md](docs/build-copy-flash.md).

## 3. Install to internal eMMC

Run this from the working SD system. It has two stages:

1. **Bootloader:** `port/internal/boot0-install.sh --check`, then `--apply`.
   This writes the BCT and U-Boot into the eMMC's hardware boot0 area, then
   verifies the readback and restores write protection. After this, a normal
   power-on boots without APX. U-Boot reads `/boot/extlinux/extlinux.conf`
   from the SD card first, then from the eMMC.
2. **Root filesystem:** `port/internal/user-area-install.sh --apply`. This
   writes the internal root image and verifies every byte it wrote. It then
   expands the partition and filesystem.

Then rename the SD card's `extlinux.conf` to `extlinux.conf.sd-recovery` so
boot falls through to the eMMC. Keep that SD card for recovery: APX plus the
SD payload still starts it.

Building the internal images and the details of each check are covered in
[docs/build-copy-flash.md](docs/build-copy-flash.md#generate-the-checkpoints-internal-images)
and [docs/internal-install.md](docs/internal-install.md). Later kernel
updates only replace files in `/boot` through extlinux. U-Boot does not need
to be reflashed.

## Repository layout

| Path | Contents |
| --- | --- |
| `port/` | Device tree, kernel/Mesa/opentegra patches, N-Trig SPI driver, install scripts, image input locks |
| `port/source-diffs/` | Uncommitted changes captured from the local upstream checkouts, still to be merged into the patch series |
| `scripts/` | Build, image, flash, transfer and on-device test tools |
| `tools/` | Dockerfiles for the pinned build containers |
| `docs/` | Bring-up notes and hardware evidence |
| `sources.lock.json` | Upstream repositories, pinned by commit (not vendored) |

Clone each entry in `sources.lock.json` into `sources/<name>` at its pinned
commit, then apply the patches from `port/`.
