# Indigo hardware window presentation

The next checkpoint verifies server-pixmap sharing and a nested Weston hardware
compositor, including a required kernel DMA-BUF fix. See
[gpu-compositor.md](gpu-compositor.md) for the current results. The evidence
below preserves the earlier window-presentation checkpoint.

The private Mesa 26.2.3 Grate build now creates hardware EGL and GLX contexts
through a patched Opentegra DRI3 path. Actual pixels read through Xorg match
the GPU-rendered window at 256x256, 400x300, 400x301 and native 800x1280.
This is a window-presentation checkpoint. A desktop compositor using this
Mesa build has not yet been verified.

The build and evidence identities are recorded in
[gpu-dri3-checkpoint.json](gpu-dri3-checkpoint.json). Raw results live in
[evidence/grate-20261006-dri3](evidence/grate-20261006-dri3).

## Implementation

The existing Xorg driver exposes DRI2; the newer Mesa branch removed its DRI2
client path. The bridge adds DRI3 version 1 callbacks to the pinned Opentegra
source, using its existing PRIME and EXA helpers. Clients receive a render-node
descriptor. Single-plane linear RGB buffers become EXA pixmaps with checked
depth, pitch, allocation size and tiling. Imported and exported buffers bypass
compression and BO reuse caching.

Pixmap export materializes pending drawing and waits for its fences. Pooled
pixmaps migrate to a dedicated BO before export, preserving visible rows and
avoiding disclosure of neighboring pool entries. The export callback is
implemented but still needs a direct protocol round-trip and compositor test;
the passing window tests exercise client-buffer import and presentation.

The bridge initializes Xorg's shared-memory fence support and Present's copy
path. Present uses the server's fake vblank mechanism; no native vblank
callbacks or page flips are advertised. The copy path preserves the current
rotated display. EXA must load before this Clang-built module; the trial's
private Xorg configuration explicitly loads it.

Mesa patch 0016 backs shared RGB buffers with complete bottom blocks for EXA's
16-byte block alignment. The visible image size stays unchanged. A 400x301
window allocates 304 rows and passes presentation. This padding is not claimed
to fix the earlier stale frame at 400x300, whose height was already aligned.

The cross-build uses ARMv7 hard-float musl and VFPv3-D16 without NEON. Small
compatibility fixes remove a GCC-only FP16 option and adapt the bundled sync
and string-copy code to current musl.

## Device validation

The final uninstrumented runs passed 36 Xorg RGB samples across six contexts:
one 256x256, three 400x300, one native 800x1280 and one 400x301. Each context
presented red, green and normal half-alpha red-over-blue frames. Top/bottom
samples also checked orientation. An additional 400x300 diagnostic passed six
Xorg samples and recorded matching GPU readbacks before presentation. The
normal probe does not perform that extra GPU readback.

GLX reports direct rendering, Grate/Tegra and `Accelerated: yes`, with OpenGL
2.0 and GLES 2.0. These reported versions do not establish full conformance.

The final Mesa artifact also passed the 1,107 normal blend-state comparisons
against softpipe at tolerance 2, the 331 base fragment samples and the 367
fragment/SFU samples at tolerance 10. Coverage and actual renderer identity
were checked. The 331 base samples overlap the larger fragment suite.

After restoring the original module path, XFCE was running, the display was
800x1280 rotated left, Xorg enumerated N-Trig touch, pen and GPIO keys, and a
Wi-Fi ping succeeded. Physical touch, pen and a fresh SD boot were not tested
in this stage. The distribution driver remains selected for ordinary boots.

## Failures preserved for follow-up

GDB traced the first presentation crash to the existing DMA-BUF import helper.
It queried `SEEK_CUR`, which DMA-BUF does not support, interpreted its errno as
a failed size query, then freed a BO with uninitialized lists. The replacement
uses the supported `SEEK_END` query and the existing `drm_tegra_bo_wrap` handle
cache and initialization. The crash stopped after this change. The next error,
`xcb_dri3_fence_from_fd failed`, stopped after `miSyncShmScreenInit` was added.

One earlier 400x300 blended frame retained the previous green content. Later
uninstrumented repeats passed, but the cause remains unproven. Sustained swaps
and the older intermittent NPOT texture corruption remain open.

A valid GLES client-vertex-array probe also triggered a 1 MiB staging allocation
and legacy job submission errors (`invalid class id 0x0`, `-22`). The final
probe uses explicit vertex buffers, as the existing passing shader probes do.
The client-array path still needs investigation. Earlier CMA allocation
failures remain recorded; changing CMA free counts alone does not prove a leak.

## Rebuilding and running a reversible trial

```sh
scripts/build_mesa_grate.sh candidate
scripts/build_opentegra.sh
```

The Mesa artifact is `build/mesa-grate-candidate-armv7.tar.gz`. The Xorg module
is `build/opentegra-dri3/src/.libs/opentegra_drv.so`; its build metadata and
presentation probe are `build/opentegra-dri3-build.json` and
`build/opentegra-dri3-gpu-present-check`. Source revisions and patch stacks are
pinned and checked. Alpine edge packages and container inputs are not fully
pinned yet, so complete reproducibility remains pending.

Install Mesa with the existing checked private-prefix installer. Transfer the
module, presentation probe and `scripts/tablet_dri3_trial.py` to `/tmp` on the
tablet. Compute the module's SHA256 on the host and pass that exact digest:

```sh
python3 /tmp/tablet_dri3_trial.py --module /tmp/opentegra_drv.so --sha256 HOST_SHA256
```

The script requires root and verifies the external SD controller. It installs
under `/opt/indigo-xorg/dri3`, creates a temporary LightDM override, restarts
the session and automatically restores the ordinary module path after 180
seconds. Its printed token also permits an early restore:

```sh
python3 /opt/indigo-xorg/dri3/trial.py --restore TRIAL_TOKEN
```

During the trial, select the candidate Mesa for the test process:

```sh
su julian -c 'DISPLAY=:0 XAUTHORITY=/home/julian/.Xauthority INDIGO_MESA_REVISION=ad06de32d309 /usr/local/bin/indigo-gpu-run /tmp/gpu-present-check 800x1280'
```

The next stage is a compositor workload compatible with the reported graphics
API, including server-pixmap export, texture import and repeated damage/swaps.
After stability and memory-pressure work, pin full build inputs, integrate the
private drivers into the SD image, then verify a fresh boot and physical input.
