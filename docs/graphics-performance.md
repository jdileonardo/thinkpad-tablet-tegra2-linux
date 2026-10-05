# Indigo graphics and performance measurements

Measured on the physical ThinkPad Tablet on 2026-10-05, running
`7.0.1-nura-indigo-ram`, Nura edge ARMv7, XFCE/X11 and Mesa 26.2.4.
The desktop and USB diagnostic shell remained running. No clock, governor,
global rendering environment or display-manager configuration was changed.

## System measurements

| Check | Observed result | Meaning / scope |
| --- | --- | --- |
| CPU clock | 1 GHz (`pll_x` / `cclk`) | Read from kernel clock summary; cpufreq sysfs policies are absent |
| Idle RAM | 258 MiB used, 731 MiB available, 990 MiB total | Snapshot before diagnostic tool installation |
| Swap | 1,484 MiB zram, zero used | Zero swap use throughout sampled CPU/memory/graphics tests |
| Idle temperature | 33°C CPU thermal zone | Separate initial snapshot |
| CPU, one thread | 37.89 events/s | sysbench CPU, prime limit 10,000, 10 seconds |
| CPU, two threads | 72.46 events/s | Same workload; 1.91× throughput, approximately 97.8% aggregate CPU use |
| Sequential memory write | 486.62 MiB/s | sysbench, one thread, 16 MiB buffer, 1 GiB total; approximately 2.1 seconds |
| SD write including fsync | 18.49 MiB/s | Dedicated 64 MiB temporary file on verified external-SD root |
| SD direct read with data verification | 15.98 MiB/s | O_DIRECT with an aligned 1 MiB buffer; includes Python comparison overhead |
| Peak system-test temperature | 38.75°C | Short tests, not a sustained thermal stability qualification |
| Root filesystem | 58.6 GiB, approximately 57.6 GiB free | Snapshot before diagnostic packages |

The storage test generated data before starting its timer, used file I/O rather
than raw disks, and removed its private temporary directory afterward. O_DIRECT
bypassed the OS page cache; card-internal caching is not controlled. The memory
test measures this particular scalar workload, not theoretical DRAM bandwidth.
The prime-test rate is useful for comparing runs with identical parameters,
not as a general cross-device performance score.

Evidence:

- `diagnostics/graphics-performance-baseline.txt`
- `diagnostics/system-bounded-benchmarks.txt`
- `diagnostics/indigo-system.json` (samples, commands, output and summary)

## Graphics result

Xorg's `opentegra` driver reports EXA hardware acceleration and composition,
and the display, portrait rotation and touch work. This does not establish
accelerated OpenGL rendering.

Actual GLX and X11 EGL queries return **llvmpipe (LLVM 23.1.2, 128 bits)**,
with `Accelerated: no`. GL advertises OpenGL 4.6 and OpenGL ES 3.2. Those
advertised capabilities are not proof that drawing works. X11 EGL also warns
that it cannot obtain a DRI3 device.
Direct EGL/GBM and surfaceless queries initialize but also select llvmpipe;
moving to a native compositor does not automatically select hardware rendering.

Both 400×300 and native 800×1280 glmark2-es2 offscreen tests terminate with
`Illegal instruction`, exit 132, before completing their first build scene.
There is consequently **no valid FPS result**. Each attempt used explicit
frame completion (`--frame-end finish`) and bounded execution. Peak sampled
temperature was 36.25°C, with no swap use; this failure is not explained by
thermal throttling or exhausted RAM in these tests.

GDB stopped at `vmov d16, r1, r0` in an anonymous executable mapping, followed
by another move to `d17`. This CPU reports `vfpv3d16` and no NEON in
`/proc/cpuinfo`: registers d16/d17 lie outside its supported 16-register
VFP bank. The trace identifies the immediate fault as incompatible generated
code. LLVM's live host query returns CPU `cortex-a9` and features
`+vfp3,+vfp3d16,+fp16`. Determining which part of LLVM/Mesa's feature handling
loses the register-bank constraint requires further investigation. The stripped
JIT frame lacks a full symbolic backtrace.

A process-local `GALLIUM_DRIVER=softpipe` override also fails, but earlier:
EGL cannot initialize, and GLX cannot create its software screen. This renderer
is not a usable fallback in the current installation. No fallback override
was installed globally.

Kernel logs also contain recurring 132,710,400-byte DRM allocation failures.
These already occurred during earlier battery/rotation diagnostics, before
these rendering benchmarks. Their allocation path remains a separate graphics
investigation; no relationship to the JIT's illegal instruction is established.

Evidence:

- `diagnostics/graphics-renderer-capabilities.txt`
- `diagnostics/graphics-bounded-benchmarks.txt`
- `diagnostics/indigo-graphics.json`
- `diagnostics/graphics-softpipe-benchmarks.txt`
- `diagnostics/indigo-softpipe.json`
- `diagnostics/graphics-illegal-instruction-backtrace.txt`
- `diagnostics/graphics-jit-features-and-final-state.txt`
- `diagnostics/graphics-direct-egl-platforms.txt`

## Consequence for Plasma Mobile

CPU, available RAM and storage appear usable for continuing the port. These
short measurements do not establish how much memory Plasma itself will use.
The graphics stack is the immediate issue to resolve before a meaningful
Plasma/KWin GL trial: the current software renderer cannot draw this basic
workload, and GPU-accelerated rendering has not been demonstrated.

A current hardware-driver source exists in Libre Tegra's Mesa fork:
https://codeberg.org/libre-tegra/mesa, branch `grate-26.2.3`, observed commit
`2a7bf9cc5eb1b9ab07373c1814cd1320073af450`. Its actual
`src/gallium/drivers/grate/meson.build` contains the Grate Gallium driver and
Tegra DRM integration. It has not been built or tested on this unit. Investigate
a private/staged build of this driver and a compatible software fallback,
then repeat the drawing and Wayland checks.

## Repeating the measurements

The SD card currently has `mesa-utils`, `glmark2`, `sysbench` and `gdb`
installed. Rootfs build defaults were not expanded to include these diagnostic
packages. The reusable measurement script is
`scripts/measure_tablet_performance.py`; it refuses its storage test unless the
root controller is external SD `c8000400` and `/var/tmp` is on that root.

After uploading the script to `/tmp` through `ram_transfer.py`, run on the
tablet's diagnostic console:

```sh
python3 /tmp/measure_tablet_performance.py --phase system --output /tmp/indigo-system.json
python3 /tmp/measure_tablet_performance.py --phase graphics --output /tmp/indigo-graphics.json
python3 /tmp/measure_tablet_performance.py --phase graphics --driver softpipe --output /tmp/indigo-softpipe.json
```

Then download each report with `ram_transfer.py download`. Run phases separately
so their CPU, memory and I/O workloads do not overlap. A graphics retry is useful
after changing the renderer; the current llvmpipe failure is already reproducible.
