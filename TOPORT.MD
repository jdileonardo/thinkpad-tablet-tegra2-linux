# ThinkPad Tablet Indigo: remaining Linux bring-up

Assessment date: 2026-10-06; updated after the 2026-10-07 UTC live checks.
Target: the original Lenovo ThinkPad Tablet, Tegra20, running the custom
Nura kernel and XFCE from internal eMMC.

This backlog combines source, stock backups and saved hardware evidence with
the [live CPU/backlight checks](docs/power-bringup.md). The entries below
distinguish missing integration from features that need physical testing.

The intended workload is a docked calendar display and Spotify controller.
Local Spotify audio playback is not currently a requirement.

## Working baseline

The latest [SD-image checkpoint](docs/xfce-image.md#card-write-and-remaining-hardware-checks)
records two APX boots with XFCE autologin, automatic Wi-Fi reconnection,
network time synchronization and matching runtime artifact hashes. Physical
touch, rotation and all four front buttons have been confirmed.

Display and selected graphics paths work, with documented driver limitations.
The image includes the graphics allocation fixes and N-Trig watchdog recovery.
Long-duration reliability and recovery from a spontaneous silent touch
controller remain separate validation work.

[Persistent U-Boot and internal Linux installation](docs/internal-install.md)
are complete; ordinary restarts boot XFCE without an APX download. Keep the
known-good APX/SD recovery path. Physical SD removal and cold power-on remain
a separate user check.

The missing custom-kernel Tegra20 cpufreq module is now installed on internal
Linux and configured to load automatically. Live requests verified 216 MHz,
608 MHz and 1 GHz, with CPU voltage changes; the ondemand governor responds to
load. CPU thermal cooling support still requires a kernel configuration change
and its own hardware trial. The previously frozen image does not include this
incremental module installation. The current default input lock and assembler
now include it for the next build, with module/startup verification in both SD
and internal image paths; no new full image has been flashed.

## Bluetooth: a promising next port

Bluetooth appears to need board integration and matching modules rather than
a new controller driver. This is an engineering assessment, not a successful
Bluetooth test.

### Evidence already available

- Stock Android's `init.ventana.rc`, inspected inside
  `build/stock/ramdisk.cpio.gz`, starts `brcm_patchram_plus` on `/dev/ttyHS2`
  at 3,000,000 baud, using `/etc/firmware/` and low-power-mode support.
- The stock UART mapping identifies UART C, corresponding to the current
  kernel's `serial@70006200`.
- `sources/linux-stock/arch/arm/mach-tegra/board-ventana.c` specifies Bluetooth
  shutdown GPIO U0, device wake GPIO U1, host wake GPIO U6, and the 32 kHz
  blink clock.
- The saved stock system image contains `/etc/firmware/bcm4329.hcd`:
  17,179 bytes, 96 complete HCI command records, with no trailing bytes.
  SHA256: `8fd56bf6a3b0fec64b158e3d688e343fd1f73526ce3d4c2d0b261851e9b678b6`.
  Structural parsing does not establish successful firmware loading.
- The current kernel has the Broadcom UART driver and the
  `brcm,bcm4329-bt` compatible. See the
  [upstream binding](https://github.com/torvalds/linux/blob/master/Documentation/devicetree/bindings/net/bluetooth/brcm%2Cbluetooth.yaml)
  and the local `sources/linux-nura/drivers/bluetooth/hci_bcm.c`.
- BlueZ and Blueman are in the frozen rootfs package inventory.
- `port/tegra20-lenovo-indigo.dts` has no Bluetooth node. The custom
  `7.0.1-nura-indigo-ram` module directory contains only the selected input,
  reset and N-Trig modules. Available Bluetooth modules are under the
  distribution kernel's `7.0.1-postmarketos-grate` directory; they cannot be
  assumed compatible with the custom kernel.
- Stock startup references `/sys/EcControl/BTMAC` for controller-address
  handling. Address provisioning needs investigation alongside firmware setup.
  The stock implementation first writes EC register `0x49` to reset an EEPROM
  cursor, polls `0x48`, then reads three words from `0x62` and reverses the bytes.
  Repeating ordinary register reads is not sufficient; no EC writes were made
  during this investigation.
- UART C is currently disabled and unregistered at runtime. The inherited
  pinmux already selects UART C on UCA/UCB. The existing GPIO consumers do not
  claim U0/U1/U6; this does not establish their electrical startup state.
- The stock firmware was freshly extracted and reparsed: 95 vendor RAM-write
  records (`0xfc4c`) and one launch record (`0xfc4e`), matching the hash above.
  Modern `btbcm.c` requests chip-derived names such as `BCM4329B1.hcd`; the
  actual controller identity must be read before selecting that filename.

### Work remaining

1. Add the UART C Bluetooth node, verify pinmux and RTS/CTS, and describe the
   shutdown, wake and clock connections using current bindings. Confirm GPIO
   polarity and startup sequencing against the stock implementation.
2. Build and package Bluetooth modules and dependencies for the exact custom
   kernel, with a correct module dependency index.
3. Include the verified stock firmware under the filename requested by the
   modern driver. Confirm chip/revision identity before selecting firmware;
   the backup also contains a BCM4330 patch file.
4. Establish controller-address provisioning and BlueZ startup, then test
   discovery, pairing and actual keyboard/mouse input.
5. Verify reconnection after reboot, repeated connection/disconnection and
   operation during Wi-Fi traffic. Check low-power transitions and wake
   behavior when suspend work begins.

Expected effort: medium, with a promising starting point. Bluetooth audio
requires separate profile and audio-stack validation; an enumerated controller
alone is not a completed port.

## Remaining hardware and system work

Effort descriptions are relative assessments, not implementation-time estimates.

| Area | Current evidence and gap | Next useful validation or implementation |
| --- | --- | --- |
| Brightness and remaining buttons | Commands for brightness 2/4/7 change driver PWM requests; blanking disables PWM and settings were restored. Visual confirmation, side volume and power-button behavior remain unverified. | Confirm visible brightness and blank/unblank; capture side/power key events and verify desktop actions. A 60-second side-key capture had no events and establishes no physical-button result. |
| CPU power management and thermals | Matching cpufreq module is installed and autoloads; current image recipes/lock include it. Eight speeds span 216 MHz–1 GHz; clock/voltage changes and ondemand load response passed. Temperature sensor and 50°C passive/60°C critical trips exist, but `CONFIG_CPU_THERMAL` is disabled and no CPU cooling device registers. | Enable CPU thermal/frequency cooling in a candidate kernel, verify cooling-device registration and frequency limiting without heating to the critical trip. Short-trial peak was 38.75°C, not a sustained thermal qualification. |
| Audio | WM8903 and an ALSA card register. Speaker/headphone playback, microphone and jack detection are untested. Inherited Ventana microphone-enable settings differ from stock Indigo. | Verify board routing and supplies, then test playback, volume, jack detection and recording. Likely testing plus board-specific fixes. |
| USB host and dock | Host controllers enumerate. Attached peripherals and dock functions lack functional validation. | Test keyboard, mouse, storage and Ethernet, including disconnect/reconnect and VBUS behavior. Test dock functions individually. |
| Battery and AC reporting | Read-only EC telemetry works at I2C address `0x58`, but there is no Indigo Linux power-supply integration. Saved readings indicate a possible battery/charger hardware issue. | Port read-only battery/AC reporting first. Charging control and usable battery capacity require separate hardware validation. A driver will not resolve a failed pack. |
| Pen | Protocol handling and a pen input device exist. Physical testing was deferred because pen batteries were unavailable. | Verify hover, tip, pressure, buttons, eraser, palm interaction and alignment in each rotation. Primarily validation once batteries are available. |
| Light sensor and compass | Stock identifies AL3000A at `0x1c` and AKM8975 at `0x0c`. Suitable current Linux drivers are present, but Indigo has no corresponding device-tree nodes. | Verify supplies, buses and interrupts, add nodes, and validate readings/orientation. Automatic brightness is the practical light-sensor benefit. |
| Suspend/resume and shutdown | Standard `/sbin/reboot` successfully runs the OpenRC shutdown path and returns to internal XFCE; the next mount required no journal recovery. Full sleep/wake and ordinary power-off remain unvalidated. | Use standard reboot during development. Power-off requires a way to power it back on; then test controlled suspend/resume and peripheral recovery. |
| HDMI | HDMI support is inherited from Ventana; physical external output, hotplug and HDMI audio are unverified. | Test connector detection and supported display modes, then audio. Existing HDMI audio deferred-probe evidence warrants investigation. |
| GPS | Stock GPS configuration specifies `/dev/ttyHS1` at 115200 baud and standby GPIO 203 (Z3). | Verify the receiver identity/protocol, UART B wiring and power sequence; establish actual position output. Do not infer this unit's GPS path from generic modem-related Android properties. |
| Cameras | Stock board code identifies MT9D115 and MT9P111 sensors. Matching sensor drivers are absent from the current kernel tree. | Investigate sensor drivers, board power/clock sequencing and the Tegra20 capture pipeline. Substantially larger work than Bluetooth or simple sensors. |
| Hardware video decoding | Tegra VDE support is configured as a module, absent from the custom module set, and untested with applications. | Package the matching driver and validate supported streams through a compatible userspace decoder. Useful if video becomes a requirement. |
| Host-independent boot | Persistent U-Boot and internal eMMC XFCE boot have passed ordinary restart without a host download. | User confirmation of SD removal and cold power-on remains pending; retain APX/SD recovery. |

Graphics follow-ups remain documented: RGB565 rendering, KWin's missing
3D-texture requirement, other experimental shader/client compatibility issues,
and compositor shutdown behavior. These are separate from adding peripheral
support and are not all prerequisites for the selected XFCE workload.

## Suggested order

1. CPU thermal cooling integration; physical brightness and side/power buttons.
2. Bluetooth controller bring-up, pairing, input and Wi-Fi coexistence.
3. Speaker/headphone audio and USB host/dock functionality.
4. Light sensor and read-only battery/AC reporting; compass if useful.
5. Normal shutdown and suspend/resume after the relevant peripherals function.

Persistent internal boot is already implemented. Pen testing depends on
batteries. GPS, HDMI,
cameras and hardware video decoding can follow as their use becomes relevant.

## Evidence and related notes

- [Hardware map](docs/hardware-map.md): board wiring and peripheral baseline;
  some graphics status predates later milestones.
- [Porting history](PORTING.md): touch/pen, buttons, rotation, battery telemetry
  and storage preservation.
- [Performance measurements](docs/graphics-performance.md): CPU clock,
  historical absent cpufreq policies and bounded temperature measurements.
- [CPU/backlight bring-up](docs/power-bringup.md): incremental installation,
  live clock/voltage/load checks, autoload and remaining thermal work.
- [Touch watchdog](docs/touch-watchdog.md): recovery implementation and limits.
- [GPU/Plasma evaluation](docs/gpu-plasma-evaluation.md): graphics feature gaps.
- [Development workflow](docs/development-workflow.md): selected workload,
  serialized console access and eventual internal installation.
- [Latest SD-image checkpoint](docs/xfce-image.md): packaged baseline and
  fresh-image physical boot/input evidence.
- `docs/evidence/image-20261006/rootfs-packages.json`: frozen package inventory.
- `build/linux-nura/.config`: selected driver configuration; enabling a module
  here does not establish that it was built or installed.
- `build/nura-sd-20261006-touch-watchdog/rootfs/usr/lib/modules/`: module
  packaging inspected for the custom and distribution kernels.
- `backups/MP0GKR7-20261005T160450Z/system-AP.img` and
  `build/stock/ramdisk.cpio.gz`: stock Bluetooth firmware and startup evidence.

For implementation, use the existing development workflow and coordinate
tablet-console access with other threads.
