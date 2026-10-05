# ThinkPad Tablet Indigo Linux port

## Device and first RAM experiment

This project targets the original 2011 Lenovo ThinkPad Tablet, Tegra20,
ADB serial `MP0GKR7`. It does not target later Lenovo Tab products.

On 2026-10-05 the tablet successfully entered NVIDIA APX (`0955:7820`).
`tegrarcm` read its active 4,080-byte BCT and reported:

- Chip UID `0x0a7c0048445fc057`, Tegra20 SKU 8, eMMC boot device.
- Operating mode 3, **developer mode**.
- SDRAM configuration strap 1; BCT ODM data `0x300d8011`.
- Active BCT SHA256 `3d089f88af9ffaf2dec929c2b27e02d63da70b186548bdcffb95e1477beb9421`.

The first custom U-Boot download ran on the tablet and displayed startup text,
as confirmed by the user. Its automatic USB fastboot connection did not appear
on the host. The exact failure point is unresolved.

A second download bundled U-Boot, Linux 5.0-rc5 from the historical ThinkPad
port, a device tree, and a static BusyBox diagnostic initramfs. The host then
enumerated `17ef:741c`, product **Diagnostic RAM console**, as `/dev/ttyACM0`.
After fixing the diagnostic shell's controlling terminal, the USB shell
reported `5.0.0-rc5-next-20190208-thinkpad-ram`, ARMv7, with both CPUs running
and `MemTotal: 1024764 kB`. Internal filesystems remained unmounted.

Loading the matching backlight, PWM backlight, and panel-simple modules
initialized Tegra DRM, `fb0`, and a 1280×800 LVDS mode (32-bit framebuffer,
5,120-byte stride). The user confirmed readable text on the actual screen.

Loading brcmutil/brcmfmac with firmware and NVRAM extracted from this unit's
Android backup created `wlan0`; `ifconfig wlan0 up` succeeded. **No network
association or traffic test has been performed.** Old firmware produces
unsupported join-preference/rxchain warnings and lacks a CLM blob, which
needs further investigation before claiming full Wi-Fi support.

The WM8903 audio codec/card and GPIO keys register. Audio playback and
physical key events have not been tested. No touchscreen or power-supply
device is registered in this diagnostic configuration.

Evidence is saved as `diagnostics/linux-console-20261005T*.txt`.

This is an initial hardware bootstrap, not a finished Nura installation.
The historical kernel is a comparison baseline for the current Nura Tegra
kernel, not the final OS target.

## Nura SD desktop milestone

On 2026-10-05 the dedicated Indigo device tree and panel driver patch booted
the pinned Nura Tegra **7.0.1** source on this tablet. USB ACM and readable
1280×800 text were verified on the physical device. The ARMv7 Nura edge root
filesystem was then built with pmbootstrap, XFCE and OpenRC, written to the
user-authorized 64 GB SD card, and booted through the RAM-loaded U-Boot.

The user confirmed the **XFCE desktop** on the tablet. Runtime evidence shows:

- `/etc/os-release`: `PRETTY_NAME="Nura edge"`, `ID="nura"`.
- `/dev/mmcblk0p1` mounted as `/`, ext4; this controller is `c8000400.mmc`.
- Kernel `7.0.1-nura-indigo-ram`, both CPUs, approximately 1 GB RAM.
- Xorg uses `opentegra`; XFCE session and panel run as `julian`.
- Xrandr reports 1280×800 at 60.33 Hz. Hardware acceleration performance
  has not been measured; driver initialization alone does not establish it.
- GPIO keys are exposed through evdev/libinput. Physical key events remain
  untested. Matching evdev, hid-generic and USB HID modules are on the card.
- Zram swap is active. Wi-Fi currently has no interface on this newer kernel;
  historical Wi-Fi initialization does not prove current support.
- No internal Android filesystem is mounted. Android bootloader and partition
  contents were not modified by this installation.

The SD card was freshly identified as the 64,043,876,352-byte removable disk
through reader serial `201506301013`. The initial 4,296,015,872-byte image
passed full on-card SHA256 read-back (`c328bd19526cd0421b72872492f498b597fb0925c0bac9a7e95211ed6912ac62`).
Its ext4 partition was expanded across the card and passed `e2fsck -fn`.
It showed about 57.6 GiB free before first boot. Do not reuse that disk letter
or reader identity without a fresh enumeration on a future write.

Evidence: `diagnostics/nura-sd-os-console.txt`,
`diagnostics/nura-desktop-status.txt`, and
`build/nura-sd/card-write-verification.json`.

Boot still requires the host to download U-Boot and the payload through APX.
Touch/pen, Wi-Fi association, audio playback, suspend, battery and charging
need further porting and validation. This is a working development desktop,
not a complete hardware port.

## Storage preservation

The boot scripts do not flash or save U-Boot's environment, change Android
partitions, or mount internal Android filesystems. Historical and Nura RAM
diagnostic profiles mount only proc, sysfs, devtmpfs, tmpfs, and configfs.
The Nura SD profile additionally mounts the authorized external-card UUID
as the OS root; normal desktop writes go to that card.
U-Boot uses a transient environment and disables fastboot flashing/formatting.

`backups/MP0GKR7-20261005T160450Z/` contains verified boot, recovery, system,
preinstall, update, misc, SC, persdata, disk prefix and tail images. Each of
the original ten images passed its recorded SHA256 check. `manifest.json`
records block ranges and lengths; `SHA256SUMS` records hashes. `active.bct`
was subsequently read through APX and its hash is recorded above. Linux
also exposed the two 2 MiB eMMC boot regions; both were downloaded read-only
and verified against hashes computed on the tablet. Their `force_ro` flags
remained 1. `apx-linux-additions.json` records these additions and the eMMC CID.

This is **not a full eMMC or user-data backup**. Cache and userdata were not
copied. The stock kernel did not expose eMMC boot partitions; the RAM kernel
allowed the additional boot-region backups described above. Restore has
not been tested. The tablet's battery still requires separate investigation.

## Pinned sources

| Source | Revision / release |
| --- | --- |
| dpavlin/u-boot, `phj00-thinkpad-tablet` | `385640388c84e405f817f8e747d4febaa0be0de5` |
| dpavlin/linux, `thinkpad-tablet-phj00` | `8b626d0a4f6f39a6c12bf6ea4ed61744e4f7a54e` |
| NVIDIA/tegrarcm | `f6a46f1b342fe5ff531281e605b52b2a604a8aac`, v1.8 |
| NVIDIA/cbootimage | `80c499ebbe8a64aa2ee4222e6a8f342f465f6680` |
| BusyBox | 1.36.1 |
| libre-tegra/linux, current Nura Tegra target | `bfffc6d6656e87f3de3aa4c09d852849081ef088`, stable branch |

Source directories and generated binaries are excluded from version control.
Historical source preparation scripts require the exact pinned revisions.
Current Nura, pmaports and pmbootstrap checkouts are pinned in
`sources.lock.json`. Local port changes are tracked on `port/nura-kernel`.

## Rebuild the diagnostic RAM payload

Docker provides the legacy toolchain and Python 2 dependencies without changing
the host's packages. The image is `thinkpad-port-build:2026-10-05`.

```sh
docker build -t thinkpad-port-build:2026-10-05 -f tools/Dockerfile .
bash scripts/build_kernel.sh
bash scripts/build_modules.sh
bash scripts/build_busybox.sh
python3 scripts/make_ramdisk.py
bash scripts/build_uboot.sh --direct-linux
python3 scripts/make_ram_payload.py
```

The image downloads at `0x108000`; its embedded components are at:

| Component | RAM address |
| --- | --- |
| U-Boot SPL / U-Boot | `0x00108000` |
| Linux zImage | `0x01000000` |
| Initramfs | `0x02000000` |
| Linux device tree | `0x02200000` |

`build/ram-test/payload-manifest.json` records each component's size and hash.
U-Boot's automatic command sets diagnostic boot arguments and invokes `bootz`
using these addresses. It does not scan Android filesystems for a kernel.

After physically entering APX on this tablet and freshly confirming its USB
identity, the command used for the second experiment was:

```sh
timeout 45s bash scripts/tegrarcm.sh --usb-timeout=5000 \
  --bct=/work/backups/MP0GKR7-20261005T160450Z/active.bct \
  --bootloader=/work/build/ram-test/thinkpad-ram-payload.bin \
  --loadaddr=0x108000
```

`/work` paths are inside the dependency container, which binds this project.
The container receives USB access, not a privileged mode or host disks.
The original combined-image transfer log is
`diagnostics/apx-direct-linux-20261005.log`.

## USB console and driver loading

```sh
python3 scripts/ram_console.py
bash scripts/load_ram_drivers.sh
```

The latter reproduces the module transfers and loads tested manually on this
unit. Run it once on a fresh diagnostic RAM boot. It expects the firmware
files in `build/stock/firmware/`, extracted read-only from the system backup:

```sh
mkdir -p build/stock/firmware
debugfs -R 'dump /vendor/firmware/fw_bcm4329.bin build/stock/firmware/brcmfmac4329-sdio.bin' backups/MP0GKR7-20261005T160450Z/system-AP.img
debugfs -R 'dump /etc/nvram_4329.txt build/stock/firmware/brcmfmac4329-sdio.txt' backups/MP0GKR7-20261005T160450Z/system-AP.img
```

`ram_transfer.py` uploads only to `/tmp` or `/run`, and verifies downloaded
or uploaded data against device-side SHA256. `ram_console.py` verifies the
USB product identity and waits for the diagnostic shell prompt before sending
commands. An `echo -n` is required when setting the historical kernel's custom
firmware search path; a newline becomes part of that parameter's value.

The historical RAM kernel sees the whole eMMC but does not parse its NVIDIA
partition table, so Android partitions do not appear as block nodes. The
current Nura Tegra configuration enables `CONFIG_TEGRA_PARTITION=y`; this
must be checked against the captured stock partition ranges when booted.

## Rebuild the Nura SD boot

The new kernel uses the official pmaports ARMv7 configuration with USB ACM,
Wi-Fi dependencies and firmware support built in, reduced debug information,
and the Indigo device tree / fixed panel patch. The kernel build script also
builds the three matching input modules needed by the desktop.

```sh
docker build -t thinkpad-nura-build:2026-10-05 -f tools/Dockerfile.nura .
docker build -t thinkpad-pmbootstrap:2026-10-05 -f tools/Dockerfile.pmbootstrap .
bash scripts/build_nura_kernel.sh
python3 scripts/build_nura_rootfs.py
bash scripts/build_recovery_helpers.sh
```

Create an external-root UUID in `build/nura-sd-root.uuid`, then build the
initramfs using that UUID, followed by the matching U-Boot and payload:

```sh
python3 scripts/make_ramdisk.py --profile nura-sd --root-uuid "$(cat build/nura-sd-root.uuid)"
bash scripts/build_uboot.sh --nura-sd
python3 scripts/make_ram_payload.py --profile nura-sd
python3 scripts/create_nura_sd_image.py
```

The image script operates on files only and checks the ext4 filesystem before
assembling the MBR image. The writer requires an explicitly identified removable
whole USB disk, reader serial and exact size; it rechecks identity and mounts,
verifies the source hash, writes, reads back every image byte, then expands and
checks the filesystem. `scripts/write_nura_sd.py` is a destructive card operation;
only run it for a freshly identified card whose contents may be erased.

The first-login password is generated in ignored, mode-0600
`build/nura-first-login.txt`; it is not stored in Git. The development card uses
XFCE autologin for `julian` and a wired root shell on `ttyGS0` for bring-up.

The current payload layout is kernel `0x01000000`, initramfs `0x02400000`,
and device tree `0x02600000`. Earlier 32 MiB initramfs placement overlapped
the larger ARM kernel's relocated decompressor and produced a VFS root panic.
The payload builder now checks the kernel symbol map and compressed size for
that overlap, and keeps the download below U-Boot's 40 MiB startup stack.
The SD initramfs restricts root discovery to the external SD controller and
the exact UUID, and falls back to a RAM rescue shell if the card is unavailable.

Once APX is freshly identified:

```sh
bash scripts/tegrarcm.sh --usb-timeout=5000 \
  --bct=/work/backups/MP0GKR7-20261005T160450Z/active.bct \
  --bootloader=/work/build/nura-sd-test/thinkpad-ram-payload.bin \
  --loadaddr=0x108000
python3 scripts/ram_console.py --command 'cat /etc/os-release' --command 'cat /proc/mounts'
```

The root-only `reboot-into-apx` helper uses Tegra's existing `forced-recovery`
restart handler. It is installed on the development card at
`/usr/local/sbin/reboot-into-apx`, and has worked for repeated RAM boot tests.

## Next porting milestones

1. Restore BCM4329 SDIO enumeration and validate Wi-Fi association on 7.0.1.
   The stock kernel identifies Wi-Fi power K5, reset K6 and a 32 kHz blink clock.
2. Port the stock N-Trig SPI touchscreen/pen protocol. Stock wiring is SPI0,
   chip select 0, 3 MHz, power A5, output enable Q7 and interrupt V6.
3. Validate keys, audio playback, touchscreen, suspend,
   charging, and the current kernel's display driver.
   Historical support for one component does not prove it on this unit.
4. Design persistent installation only after recovery and power are established.
