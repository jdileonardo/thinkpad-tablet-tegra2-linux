# CPU frequency scaling and backlight checks

On 2026-10-07 UTC, the internally installed Indigo system initially ran at
1 GHz with no cpufreq policy. Its existing kernel config selected
`CONFIG_ARM_TEGRA20_CPUFREQ=m`, but the module was never built or packaged.
The device tree already supplied CPU operating points and the TPS6586x CPU
regulator. This required the existing Tegra20 driver, without a new driver
or device-tree change.

## Hardware results

Building and loading `tegra20-cpufreq.ko` against the configured custom kernel
created shared `cpufreq-dt` policy0 for CPUs 0/1. Available speeds are 216, 312,
456, 608, 760, 816, 912 and 1000 MHz. The default governor is ondemand.

| Controlled request | CPU clock | CPU regulator | SHA256 over 8 MiB |
| --- | --- | --- | --- |
| 216 MHz | 216 MHz | 750 mV | 0.934 s |
| 608 MHz | 608 MHz | 850 mV | 0.328 s |
| 1 GHz | 1 GHz | 1000 mV | 0.199 s |

Clock values came from `clk_summary`, voltage from `regulator_summary`, and
the frequency request was separately checked against policy sysfs. The hash
timings are a small functional check, not an application performance benchmark.
The distinction between policy requests and hardware readings is explained
in the [kernel CPUFreq documentation](https://docs.kernel.org/admin-guide/pm/cpufreq.html).

Under ondemand, five initial idle samples reached 456–608 MHz; two CPU-bound
workers drove all eight load samples to 1 GHz. Afterward the samples included
312, 456, 608 and 816 MHz. Peak temperature was 38.75°C. This short test does
not measure energy savings or continuous docked thermal reliability.

The module was installed in the custom release's module directory, `depmod`
was run, and `tegra20-cpufreq` was added to OpenRC's `/etc/modules`. A subsequent
boot loaded it automatically and recreated the ondemand policy. The kernel,
device tree, bootloader and firmware were unchanged.

Two restart checks passed module autoload. The first used the older forced
reboot procedure and the next mount replayed the journal/deleted five orphan
inodes. The second used ordinary `/sbin/reboot`, letting BusyBox init run the
configured OpenRC shutdown action; its next mount required no journal
recovery. XFCE, the rotation helper, N-Trig registration and automatic Wi-Fi
reconnection returned. Prefer standard reboot for development. This does
not validate power-off/wake, suspend/resume or physical touch after restarting.

Brightness 2/4/7 produced PWM2 duty requests of 156862, 627450 and 5000000 ns
within its 5000000 ns period. `bl_power=4` disabled PWM; the trial restored
brightness 6 and `bl_power=0`. These are driver-side observations: PWM hardware
readback returns `-EOPNOTSUPP`, and a user must confirm the visible brightness
and blank/unblank behavior. A 60-second side-key capture recorded no events;
no physical press was confirmed, so the side keys remain unvalidated.

## Repeating the incremental installation

This recipe uses the existing configured build and the current kernel
checkpoint. It is separate from assembling the earlier frozen image.
The full kernel builder now also requests this module; the targeted builder
below is sufficient for the existing checkpoint and avoids rebuilding the
kernel. The full-kernel recipe itself was not rerun for this change.

```bash
bash scripts/build_nura_cpufreq.sh
python3 scripts/ram_transfer.py upload \
  build/linux-nura/drivers/cpufreq/tegra20-cpufreq.ko /tmp/tegra20-cpufreq.ko
python3 scripts/ram_transfer.py upload \
  port/internal/install-cpufreq.sh /tmp/install-cpufreq.sh
python3 scripts/ram_console.py --seconds 5 \
  --command 'sh /tmp/install-cpufreq.sh --check'
python3 scripts/ram_console.py --seconds 5 \
  --command 'sh /tmp/install-cpufreq.sh --apply'
```

The installer verifies the running release, this unit's internal root CID and
controller, module hash and vermagic. It refuses an existing different module.
Successful loading also exercises kernel symbol-version checks; it never uses
force loading. The exact module hash is pinned in the installer, so rebuilding
against a different kernel requires a new reviewed checkpoint. Autoload is
added only after loading and policy checks succeed.

To repeat the bounded live trial, upload `scripts/tablet_power_trial.py` to
`/tmp` and run it with Python. It temporarily changes the governor, runs two
eight-second workers, checks brightness and blanks for one second. Settings
are restored in `finally`, and thermal samples stop the trial at 45°C.
Run the trial on the tablet, not on the host. An external kill/power loss
cannot be caught by Python's cleanup handler.

To disable the incremental change, remove its autoload line from `/etc/modules`
and reboot normally. Retain the module and evidence for later packaging.
The original SD recovery image has not been changed. The 66 earlier frozen
inputs remain a separate baseline; this module must be added to a new image
lock and packaging recipe before calling a new image complete.

## Remaining thermal and Bluetooth work

The live CPU zone has a 50°C passive trip and a 60°C critical trip, but
`CONFIG_CPU_THERMAL` is disabled. Thus there is no CPU cooling device even
after cpufreq loads. The next candidate kernel should enable `CPU_THERMAL`
and `CPU_FREQ_THERMAL`, then verify registration, device-tree cooling-map
binding and frequency limits. Do not claim passive throttling from a sensor
reading or trip-point listing, or deliberately heat to the critical trip.

Reading `/sys/kernel/debug/gpio` during investigation produced three
`gpiod_get_direction` WARN traces, from the GPIO debug listing. They occurred
before the power trial, not during a frequency transition. The trace and
source indicate missing GPIO `get_direction` support; GPIO drivers need
separate review. Avoid repeatedly reading that debug listing. No warning
appeared in the inspected fresh-boot log without that read.

Bluetooth UART C (`70006200`) is disabled at runtime. Existing pinmux selects
UCA/UCB for UART C. Stock code describes shutdown U0, device wake U1, host
wake U6 and the same PMC blink clock used by Wi-Fi. Clock sharing and GPIO
startup polarity need validation when adding the serdev Bluetooth child.
The [Broadcom binding](https://raw.githubusercontent.com/torvalds/linux/master/Documentation/devicetree/bindings/net/bluetooth/brcm,bluetooth.yaml)
uses a host-wakeup interrupt; the older `host-wakeup-gpios` property is deprecated.

The stock `/etc/firmware/bcm4329.hcd` was extracted afresh into ignored
`build/bluetooth/` and parsed completely: 17179 bytes, 95 RAM-write commands
and one RAM-launch command, with the previously recorded SHA256.
The modern driver derives its HCD filename from the controller identity;
read that identity before selecting `BCM4329B1.hcd` or another chip filename.
Firmware loading and redistribution rights have not been validated.

Stock `BTMAC_show` is stateful: write word 1 to EC `0x49`, poll bit 3 of
`0x48`, read three consecutive words at `0x62`, then reverse the six bytes.
No EC writes were attempted. Integrate that cursor protocol carefully with
other EC access rather than assuming ordinary register reads retrieve the
address. Controller enumeration, discovery, pairing and Wi-Fi coexistence
remain the next Bluetooth hardware milestones.

## Evidence

[Evidence directory](evidence/power-bringup-20261007/) includes the exact
module/build manifest, initial hardware state, loading and installation logs,
the full trial JSON, restart checks, GPIO warning traces and the Bluetooth
firmware structure/hash record. Firmware itself and private board backups
remain outside Git.
