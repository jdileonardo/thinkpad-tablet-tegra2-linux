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

## Storage preservation

No persistent flash, environment save, partition change, or filesystem write
from the diagnostic Linux environment is intended by these boot scripts.
The initramfs mounts only proc, sysfs, devtmpfs, tmpfs, and configfs.
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
The current Nura source is only a sparse research checkout so far.

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

## Next porting milestones

1. Implement a dedicated Indigo device tree against the current Nura Tegra
   kernel. Use historical proven hardware settings rather than renaming a
   generic Ventana image and assuming compatibility.
2. Boot a Nura ARMv7 root filesystem from RAM or removable storage.
3. Validate keys, Wi-Fi association, audio playback, touchscreen, suspend,
   charging, and the current kernel's display driver.
   Historical support for one component does not prove it on this unit.
4. Design persistent installation only after recovery and power are established.
