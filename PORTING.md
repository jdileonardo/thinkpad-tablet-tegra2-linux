# ThinkPad Tablet Indigo Linux port

The goal is Nura Linux with an XFCE desktop on this tablet, bootable from SD
and installable to the internal eMMC. See the [desktop priorities](docs/development-workflow.md#desktop-target-and-priorities).
The latest desktop result is the [rotation buffer reference fix](docs/graphics-rotation-fix.md),
following the [graphics allocation checkpoint](docs/graphics-memory.md) and
the [XFCE stability and calendar check](docs/xfce-stability.md).
The latest GPU result is the [native Wayland and Plasma evaluation](docs/gpu-plasma-evaluation.md).
See [development workflow and internal installation](docs/development-workflow.md)
for the current RAM/SD arrangement and the path toward a standalone installation.
The milestones below retain their historical scope and validation limits.

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
- GPIO keys are exposed through evdev/libinput. All four bottom buttons now
  have verified physical press/release events (see rotation milestone below).
  Matching evdev, hid-generic and USB HID modules are on the card.
- Zram swap is active. BCM4329 now enumerates and scans on this kernel;
  association and traffic still require validation (see below).
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
Touch and Wi-Fi association now work; physical pen input, audio playback,
suspend, battery and charging need further validation. This is a working development desktop,
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
builds the matching desktop input modules, the GPIO reset controller needed
by the Wi-Fi power sequence, and the experimental N-Trig SPI module.

```sh
docker build -t thinkpad-nura-build:2026-10-05 -f tools/Dockerfile.nura .
docker build -t thinkpad-pmbootstrap:2026-10-05 -f tools/Dockerfile.pmbootstrap .
bash scripts/build_nura_kernel.sh
python3 scripts/fetch_wifi_firmware.py
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

The first-login password is held in ignored, mode-0600
`build/nura-first-login.txt`; it is not stored in Git. Initially generated,
it was subsequently replaced with the user's chosen password both in that file
and on the running SD system. Rebuilding the rootfs reuses that local value.
The development card uses XFCE autologin for `julian`, disabled idle/resume
password locks, and a wired root shell on `ttyGS0` for bring-up.

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
SD desktop restarts have sometimes returned to Android instead; check APX's
USB ID before downloading, and use physical recovery entry when necessary.

## Touch, pen and Wi-Fi bring-up

BCM4329 SDIO enumeration needs the original K5 power enable, K6 reset,
and PMC blink clock. The current kernel's `mmc-pwrseq-simple` also needs
`reset-gpio.ko`, loaded from the SD root. Both the device tree and module
installation are now in the reproducible build scripts.

The original Android firmware (4.218.248.25) boots, but emits BCDC v1 packets
that the modern driver rejects: `non-BCDC packet received, flags 0x10`.
The pinned Linux firmware (4.220.48, SHA256
`d61983946b1e733e4c75dbe6841ac0f1250ebed2e3ee9058cdfdbbba3ba37c93`)
with this tablet's original NVRAM enables scanning. The tablet found `Zone`
networks after resetting the SDIO controller, and loaded the new firmware
automatically on the next SD boot. It connected to `Zone` with the laptop's
saved profile, obtained `192.168.0.174` by DHCP, passed three internet pings
(0% loss), and completed an HTTPS connectivity request. Correcting the clock
resolved TLS certificate rejection; chronyd subsequently synchronized to NTP.
The private NetworkManager profile is mode 0600 on the SD card and excluded
from Git. Evidence: `diagnostics/wifi-association-touch-test.txt` and
`diagnostics/wifi-https-clock-test.txt`.
Evidence: `diagnostics/wifi-linux-reset-result.txt` and
`diagnostics/touch-first-probe.txt`. Firmware provenance and its redistribution
license are captured by `sources.lock.json` and `fetch_wifi_firmware.py`.

`port/ntrig-spi/` contains a modern out-of-tree input driver based on the
pinned stock GPL SPI protocol. It registers separate touchscreen and pen
devices, uses Type B multitouch slots, and exposes read-only transport counts
in `/sys/bus/spi/devices/spi0.0/stats`. Its parser has passed host ASan/UBSan
checks for fragmentation, invalid lengths, corruption recovery, and a million
random bytes. Run `python3 tests/test_ntrig_parser.py` to repeat them.
`python3 tests/test_ntrig_reports.py` additionally checks the driver's actual
decoders for raw contact confidence/release, palm exclusion, report bounds,
pen hover/tip/button/eraser and pressure clamping under ASan/UBSan.

The first device probe registered both inputs, but received no valid packets.
The generic Ventana device tree tristates the SPI1 pads, unlike the stock
Indigo pinmux. An Indigo override now matches the original SPID/SPIF pull-down,
SPIE pull-up and enabled pads. This correction restored valid sensor replies
and finger reports with no parser or SPI errors. A real evdev capture contains
finger position `(4230, 6982)`, touch-down and release. XFCE recognizes the
touchscreen. Setting X/Y resolution to 42/48 units per mm, based on the
229x149 mm panel, also makes libinput accept the pen as a tablet device.
Evidence: `diagnostics/touch-pad-fix-result.txt`,
`diagnostics/touch-capture-sample.txt` and
`diagnostics/wifi-association-touch-test.txt`.
The user confirmed that touch works well and improved substantially with the
last contact-validity correction. Exhaustive corner calibration and multitouch
gestures remain separate checks. No pen report has been received yet: the user
has the pen but no batteries for it. Physical pen testing is deferred until
batteries are available; driver registration does not establish pen operation.
The raw SPI vendor confidence byte is 1 while present; the stock TrackLib
processed "removed" flag inverted that meaning. The port now uses the raw
confidence for contact state and excludes the vendor palm flag. The pen invert
flag selects the eraser tool; it is not exposed as a second barrel button.
The driver sends only the stock DRIVER_ALIVE command; it performs no sensor
firmware or calibration writes.

`scripts/input_monitor.c` is a read-only evdev capture tool for those tests.
Build it with the legacy container's `arm-linux-gnueabihf-gcc -static`; the
development tablet currently has it at `/usr/local/bin/input-monitor`.

## Buttons and rotation milestone

All four bottom buttons were physically pressed and released on the running
7.0.1 desktop. Captured codes are 153 (`KEY_ROTATE_DISPLAY`), 150 (`KEY_WWW`),
158 (`KEY_BACK`), and 172 (`KEY_HOMEPAGE`). This is the captured press order,
not a claim about their left-to-right positions. Side volume and power keys
remain separate tests.

The XFCE shortcuts installed by `port/desktop/setup-indigo-desktop.sh` are:

| Button | Action |
| --- | --- |
| Home | Toggle show desktop (`Ctrl+Alt+D`) |
| Back | Send `Alt+Left` to the focused application |
| Browser | Launch the preferred web browser; the current minimal desktop opens the application chooser because no browser is installed |
| Rotation | Lock/unlock automatic rotation; cycle orientations when no gravity reference has been configured |

Injected X11 key events verified both Home state changes, Back handler dispatch,
Browser chooser launch, and rotation lock/unlock settings. The hardware evdev
capture separately verifies all four physical keys. Setup over the USB root
shell must inherit `DBUS_SESSION_BUS_ADDRESS` from the running `xfsettingsd`
process; a separate D-Bus autolaunch can modify another xfconf daemon instead
of the active desktop. The normal XFCE autostart inherits the correct session.
The screensaver captured keys while locked during initial testing. The user's
requested convenience settings now disable `/lock/enabled` in xfce4-screensaver
and `/xfce4-power-manager/lock-screen-suspend-hibernate`; the display may still
blank for power saving, but waking it does not require typing the password.
Evidence: `diagnostics/rotation-tools-installed.txt`,
`diagnostics/unlocked-button-action-tests.txt`, and
`diagnostics/browser-key-and-auto-status.txt`.

The stock board source identifies a Kionix KXTF9 at address `0x0f` on the
`0x7000d000` I2C controller. Binding the current kernel's built-in kxcjk driver
created `iio:device0`, name `kxtf9`; dock gravity reads approximately
(-0.3, -10.0, -3.5) m/s² with scale 0.019163. The device-tree node includes
the stock Y/X/-Z mounting matrix. Its compiled DTB has been installed on the
SD card and included in the regenerated host APX payload; this node still
needs a fresh boot test. The current session uses a live I2C device binding.

With the four buttons physically along the bottom, Xrandr rotation `left`
produces an 800×1280 upright desktop. The user confirmed both upright display
and aligned touch. `indigo-rotate` changes the display and N-Trig input matrices
together, verifies both, and restores the old display and inputs on failure.
It also aligns pen pointer devices when libinput creates them on proximity;
physical pen verification remains deferred for lack of batteries.

Automatic rotation uses a recorded gravity/display reference, three matching
samples at 300 ms intervals, and holds orientation when
flat or near a diagonal. The daemon and user configuration persist through
XFCE autostart on the SD card. The current session is calibrated and automatic
rotation is enabled. The first physical left/right quarter-turn test rotated
both landscape positions upside down: the raw gravity and Xrandr directions
had opposite signs. Subtracting the measured gravity direction fixes the
mapping; the updated controller is installed and its corrected orientation
tests pass. The user subsequently confirmed that physical rotation works correctly.
Run `indigo-rotate status`, `lock`, `auto`, or `calibrate` inside the desktop
session to inspect or change it. Logs are in
`~/.local/state/indigo-tablet/{rotation,buttons}.log`.
Evidence: `diagnostics/manual-portrait-rotation.txt`,
`diagnostics/accelerometer-bind-and-package-trust.txt`, and
`diagnostics/persist-accelerometer-and-live-rotation.txt`.
Host geometry, ambiguous gravity and partial-failure rollback tests pass:
`python3 tests/test_indigo_rotation.py`.
The password change and both lock settings were applied live. A forced screensaver
activation/deactivation returned to the desktop without a password dialog.
Evidence: `diagnostics/rotation-sign-and-password-lock-fix.txt`,
`diagnostics/password-and-unlocked-screensaver-verification.txt`, and
`diagnostics/verify-user-password.txt`.

Package installation exposed an image-generation bug: pmbootstrap's temporary
key bind mounts left `/etc/apk/keys` empty in the copied image. Restoring the
installed key backups from `/usr/share/apk/keys` fixed repository signature
validation, and xinput, xdotool and i2c-tools installed successfully. No untrusted
package bypass was used. The image assembler now restores keys and installs
the desktop tools, autostart and user rotation defaults. These changes are
live on the existing SD card; the original exported image has not been rebuilt.

## Battery investigation

Android's initial, second and final captures all reported an AC supply, battery
present, 0%, 3.351 V, 20.7 °C, and `Not charging`. These were actual EC register
reads in the stock driver, rather than hardcoded voltage/temperature defaults.
However, the driver's `Good` health result is only based on nonzero design
capacity at register `0x08`; it does not establish cell health.
Evidence: `diagnostics/battery-{initial,second,final}.txt`,
`diagnostics/power-supplies.txt`, and
`sources/linux-stock/drivers/power/EC_battery.c`.

The current Nura kernel exposes no power supplies because the Indigo EC driver
has not been ported. Nevertheless, the EC is accessible at I2C address `0x58`
on the PTA branch of controller `0x7000c400`: runtime adapter `i2c-5`, device-tree
path `/i2cmux/i2c@1`. Do not confuse this with hardware controller I2C3 at
`0x7000c500`, or assume adapter numbering remains fixed in future builds.

Read-only SMBus word transactions using the stock driver's telemetry commands
returned 0% (`0x00`), 2674 mV (`0x01`), full capacity raw 2292 (`0x07`), design
capacity raw 2405 (`0x08`), unavailable/zero temperature (`0x0a`), and charging
status 2, meaning not charging (`0x0b`). Capacity units are not established;
stored full/design numbers do not prove usable capacity. No charge-control,
reset, EEPROM or firmware commands were issued. The voltage reading is not
an independent multimeter measurement. A depleted/failed pack or protection
fault is plausible; temperature/telemetry or charger faults are not ruled out.
Evidence: `diagnostics/battery-linux-initial.txt`,
`diagnostics/battery-i2c-controller-map.txt`,
`diagnostics/battery-ec-read-only-registers.txt`, and
`diagnostics/battery-ec-repeat-readings.txt`.

Lenovo's original Hardware Maintenance Manual lists a 24 Wh, two-cell Li-ion
assembly, FRUs `42T4963` and `42T4965`. Verify the installed label, connector,
dimensions and replacement provenance before ordering. The manual's power
checkout explicitly tests dock power with the battery removed, so a dock-only
configuration is a supported diagnostic option; Linux operation in that physical
configuration has not been tested on this unit. Manual pages 24 and 36–40 cover
power checkout and battery removal. Source:
https://thinkpads.com/support/hmm/hmm_pdf/tp_tablet_hmm_en_0a96158_04.pdf

The complete manual is already saved locally as
`diagnostics/lenovo-hardware-manual.pdf` (SHA256
`54c40ceb5833d9b2fd3308fca93ccc70b99f39dfcc8cd577e3daed94c32c294f`), with searchable
text alongside it. The user's intended use is docked; battery hardware tests
are deferred because no testable pack is available. Battery reporting may be
ported independently, but validated charging control is not a prerequisite
for a docked Plasma Mobile trial.

## Plasma Mobile trial prerequisites

The current SD desktop runs XFCE/X11 and OpenRC. Runtime inventory confirms
Mesa EGL/GBM/GLES packages, `/dev/dri/card0`, `/dev/dri/renderD128`, and a Tegra
DRI loader. Actual rendering checks subsequently identified llvmpipe software
rendering and reproducible illegal-instruction failures during drawing; see
`docs/graphics-performance.md`. Initial available memory was approximately
696 MiB, with 293 MiB used and no zram swap in use.
`diagnostics/plasma-readiness-inventory.txt` captures that earlier inventory.

Before installing Plasma, validate EGL/OpenGL ES and the actual renderer,
then run a minimal Wayland compositor to check the panel, touch and memory
behavior. Also boot the updated baseline once to confirm the new accelerometer
DTB, autostart, button configuration and Wi-Fi survive reboot, keeping the USB
diagnostic shell available for recovery. XFCE remains the working reference.
The current graphics checks have exposed a prerequisite fix: the Mesa JIT emits
an instruction accessing an unsupported floating-point register on this CPU.
CPU/memory/storage measurements completed successfully; full rendering and
Wayland checks remain pending a usable renderer. Subsequent GPU work passes
basic hardware triangle drawing and X11 presentation with patched Grate Mesa
25.1.9, plus a working private softpipe fallback. Shader arithmetic, constants,
textures and blending remain incomplete, so it has not been selected globally.
See `docs/gpu-driver.md` for the compatible ABI, patches and physical evidence.
An isolated Mesa 26.2.3 NIR candidate now passes shader constants, uniforms,
arithmetic, texture sampling and a matrix-transform check after adapting its
kernel interface and fixing tiny RGBA row stride. Blending and special-function
shader operations initially failed measured comparisons. A subsequent SFU
compiler extension and Tegra20 multi-instruction sequencing workaround now pass
all shader cases in the expanded 367-sample harness. Two runs pass 367/367; one
passes 366/367 with intermittent NPOT texture corruption. Blending and texture
stability remain open. Source, artifact and sample evidence are in
`docs/gpu-sfu-checkpoint.json`. It remains per-process;
system integration and compositor validation are pending. The sequencer write
now preserves MIN_OUT, and large off-screen allocations use existing GART
support to avoid CMA allocation failures. The final expanded checks pass
367/367 in three runs. Mesa 26 lacks the X server's DRI2 presentation path;
native EGL/GLX currently fall back to softpipe. Blending is still incomplete.
See `docs/gpu-integration-checkpoint.json` and `docs/gpu-driver.md`.

The follow-up reuses opentegra's destination-fetch and FDC invalidation code.
An opt-in hardware alpha-over probe now matches all 99 software-reference
samples in three runs, including overlapping primitives and textured alpha.
Normal blend-state integration remains pending; the general shader regression
still reproduces one intermittent NPOT failure. See `docs/gpu-blend-checkpoint.json`.

During the Plasma trial, replace the Xrandr/xinput rotation helper and XFCE
shortcuts with compositor-native display/input rotation and Plasma bindings.
The existing sensor's mounting matrix and physical orientation must be verified
through iio-sensor-proxy/KScreen, rather than assuming the X11 calibration applies.
Confirm the on-screen keyboard and keep the user's automatic login and disabled
password-lock preference in the test session.

The pinned Plasma Mobile UI package supports armv7, but its OpenRC install hook
enables tinydm and selects Plasma at startup. Do not install it without accounting
for the existing LightDM session. Current Nura guidance favors systemd for Plasma
and describes OpenRC integration as unmaintained. Decide the trial's service/session
layout after the graphics probe; a separate test rootfs is an option that preserves
the known working XFCE environment. References:
`sources/pmaports/main/postmarketos-ui-plasma-mobile/APKBUILD`, its OpenRC
post-install hook, https://plasma-mobile.org/ and
https://nura.eco/blog/2026/06/21/v26.06-release/.

Audio playback, volume/power keys, brightness controls, USB host/Ethernet,
suspend/resume, pen input and battery integration remain follow-ups. They do not
all need to be completed before testing whether Plasma performs acceptably.

## Next porting milestones

Wi-Fi reconnected automatically on the next APX/SD boot, and chronyd
subsequently corrected the initial 2009 RTC date without a manual clock set.
Evidence: `diagnostics/reboot-wifi-input-validation.txt` and
`diagnostics/touch-validity-reload.txt`. HTTPS can fail during the brief interval
before the first NTP synchronization.

1. Follow up on physical pen input once the user has batteries: hover, tip,
   pressure, side button and coordinate mapping. Touch is user-confirmed working;
   exhaustive corner calibration and multitouch gestures remain follow-ups.
2. Validate physical rotation lock, side volume and power keys,
   audio playback, touchscreen gestures, suspend,
   charging, and the current kernel's display driver.
   Historical support for one component does not prove it on this unit.
3. Design persistent installation only after recovery and power are established.
