# Indigo nested hardware compositor

Weston 16.0.0 now composites Wayland surfaces using the private Mesa 26.2.3
Grate/Tegra driver on the physical tablet. Two final runs each passed 48 Xorg
pixel samples across 12 changing frames. Both full 640x480 captures and sample
logs match the private softpipe reference exactly. This verifies a nested
hardware compositor; native DRM Wayland and Plasma Mobile remain untested.

![Final red background with a half-transparent white subsurface](evidence/grate-20261006-compositor/weston-final.png)

Build identities, scope and evidence hashes are in
[gpu-compositor-checkpoint.json](gpu-compositor-checkpoint.json). This builds
on the earlier [DRI3 window-presentation checkpoint](gpu-dri3.md).

## What was fixed

Opentegra's existing PRIME export helper requested only `DRM_CLOEXEC`. A client
could not map the returned FD with write access (`mmap: Permission denied`).
Patch `port/opentegra/0002-export-read-write-dma-buf.patch` adds `DRM_RDWR`.

The new direct DRI3 probe exports server pixmaps at 8x8, 63x37 and 640x480,
maps the actual DMA-BUF, imports an alias pixmap, writes through the mapping,
and performs eight alternating Xorg updates through both pixmaps. It checks
shared bytes and Xorg readbacks. Each run passes 87 samples; two runs pass on
the final kernel. These sizes exercise small and larger allocation paths,
including padded pitch/height. The test is independent of Mesa.

Using `DMA_BUF_IOCTL_SYNC` exposed an existing kernel bug. The Grate driver
called streaming DMA synchronization on every `bo->sgt`, including coherent
allocations. For those allocations `dma_get_sgtable()` creates an unmapped
description: its DMA address fields are unset. On this ARM kernel the sync
path can consequently touch unrelated low physical pages and set their
`PG_dcache_clean` / `PG_arch_1` flags. The allocator reported `BUG: Bad page
state` with those flags and low PFNs. Raw pre-fix evidence is retained.

Kernel patch `port/0002-grate-sync-only-streaming-dma-bufs.patch` restricts the
CPU-access callbacks' cache maintenance to `bo->pages`, the scattered-page
allocations with a streaming DMA mapping. Coherent allocations keep their
existing mappings and require no such cache maintenance. This follows the
[kernel DMA API's distinction between coherent and streaming allocations](https://www.kernel.org/doc/html/latest/core-api/dma-api-howto.html).
Sparse-buffer direction handling was not changed in this patch.

The rebuilt kernel was RAM-downloaded through freshly identified APX and
booted the existing external SD. Its version is still
`7.0.1-nura-indigo-ram`, now build `#3`, with artifact hashes recorded in the
checkpoint. All five installed input/reset module hashes match the rebuild,
so module replacement was unnecessary. No internal Android storage was written.
Repeated sharing, compositor and native presentation tests produce no new
kernel faults. Taint remains 12288, the existing out-of-tree/unsigned module
bits; the bad-page bit is absent. This is bounded validation, not proof of
long-term memory safety.

## Compositor validation

Weston's documented [nested X11 backend and GL renderer](https://wayland.pages.freedesktop.org/weston/toc/running-weston.html)
allow this test inside XFCE. Installed package versions are 16.0.0-r0 for
`libweston`, `weston`, `weston-clients`, `weston-backend-x11` and
`weston-shell-desktop`. The private driver is selected per process. Weston
logs GLES 2.0, GL vendor Grate, renderer Tegra and `Using GL renderer`.

The fixture creates an opaque fullscreen Wayland SHM surface and a separate
192x128 premultiplied-alpha subsurface at (32,32). Twelve frames cycle blue,
green and red backgrounds with red, blue and white translucent layers.
Expected colors are computed independently. The client creates no GL context;
Weston performs the actual GPU texture upload, sampling, drawing and blending.
Four samples per frame are read through Xorg's `XGetImage`, and a separate
capture program records the final visible window while the fixture is alive.

Early fixed-delay trials sampled Weston's startup fade, and the slower software
renderer retained an earlier frame at a 500 ms sampling point. The final fixture
waits for Wayland frame callbacks, allows the first shader compilation/fade to
settle, then checks subsequent frames. One later run was interrupted by the
180-second Xorg restore timer; the runner now refuses to start unless at least
70 seconds remain. These failures are retained, not counted as passing runs.
The deliberate waits mean this fixture provides no FPS or latency measurement.

Both final hardware runs pass 48/48 at tolerance 2. The software reference
passes 48/48, with byte-identical sample logs and entire RGB captures. The final
capture has exactly 24,576 pink pixels (255,128,128) and 282,624 red pixels
(255,0,0). The original native 800x1280 EGL presentation probe also passes all
six samples on the rebuilt kernel.

Weston logs `BUG: finalizing a layer with views still on it` during termination
in both hardware and software runs. No Weston process remained after cleanup;
the shutdown warning remains a follow-up item. It is not a kernel fault.

## Rebuild and repeat

```sh
bash scripts/build_nura_kernel.sh
python3 scripts/make_ram_payload.py --profile nura-sd
scripts/build_opentegra.sh
```

Use the existing checked APX RAM-download workflow in [PORTING.md](../PORTING.md)
to boot the fixed kernel first. Keep the prior payload for recovery. The Mesa
artifact is unchanged from the DRI3 checkpoint. The driver builder also builds
`opentegra-dri3-share-check`, `opentegra-wayland-compositor-check` and
`opentegra-x-window-capture`, with hashes in `build/opentegra-dri3-build.json`.

Stage those probes under `/tmp/indigo-dri3` using their executable names in the
runner (`dri3-share-check`, `wayland-compositor-check`, `x-window-capture`), and
stage `scripts/tablet_compositor_trial.py`. Start a fresh reversible DRI3 trial
using [the existing trial instructions](gpu-dri3.md#rebuilding-and-running-a-reversible-trial).
Then run as the desktop user:

```sh
su julian -c 'python3 /tmp/indigo-dri3/compositor-trial.py --label weston-trial'
su julian -c 'python3 /tmp/indigo-dri3/compositor-trial.py --software --label weston-reference'
```

Use distinct labels. The runner checks the external SD, renderer identity and
remaining restore time, records logs/capture under `/tmp`, and terminates Weston
on exit or test failure. Root's early restore remains available.

## Remaining work

The ordinary XFCE driver was restored. Wi-Fi ping works, the rotation watcher
returns the display to 800x1280 left, and Xorg enumerates touch, pen and GPIO
buttons. Physical touch/rotation confirmation is still pending for this boot.
The pen and battery remain the previously agreed follow-ups.

Native DRM Wayland, hardware Wayland client buffers, Plasma/KWin compatibility,
unpaced animation performance, sustained swaps, client-array submission and
the earlier intermittent NPOT/stale-frame failures still need investigation.
The Weston log reports no EGL Wayland-display binding extension; SHM clients
work, but that does not establish accelerated Wayland-client interoperability.
Source revisions and patches are pinned, while full package/container pinning
and inclusion of the private GPU builds in an exported SD image remain pending.
