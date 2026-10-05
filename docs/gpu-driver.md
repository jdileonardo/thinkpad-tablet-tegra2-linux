# Indigo Grate GPU build

The device runs Libre Tegra's experimental kernel driver, selected by
`CONFIG_DRM_TEGRA=y` and `CONFIG_GRATE_HOST1X=y`. In this kernel tree,
`drivers/gpu/drm/Makefile` maps `CONFIG_DRM_TEGRA` to **grate/**; the upstream
driver in **tegra/** is selected separately by `CONFIG_DRM_TEGRA_ORIG`.
Reading the upstream header alone therefore does not identify the active ABI.

On the physical tablet, the experimental version ioctl reports SoC enum 0
(Tegra20), UAPI version 99997. Legacy channel ioctls open and close both
GR2D class 0x51 and GR3D class 0x60 successfully.

Libre Tegra Mesa branch `grate-26.2.3`, commit
`2a7bf9cc5eb1b9ab07373c1814cd1320073af450`, targets upstream Tegra's channel
interface. Its channel-open command number collides with this kernel's
experimental version ioctl. The call succeeds but returns version-query data,
and the Mesa channel-version validation rejects it with ENOTSUP. Its private
softpipe fallback passes a GLES2 triangle pixel check; this is software rendering.

The build in `sources.lock.json` instead pins Libre Tegra Mesa **grate-25.1.9**,
commit `647c79415a02cad7a39cb666ca26a17e45bf12df`. Its Grate driver includes
`drm/opentegra_drm.h`, `drm/uapi_v1/` and `drm/uapi_v2/`, matching the experimental
interface. On the physical tablet, the patched build passes an attribute-color
GLES2 triangle test with exact red center and blue corner pixels. GLX reports
Grate/Tegra, direct rendering and **Accelerated: yes**. An X11/EGL window also
reads back a red center and presents successfully. Context teardown exits cleanly.

This is **initial hardware 3D bring-up**, not a complete GLES2 implementation.
The source still has major gaps: vertex immediates are referenced without being
uploaded, fragment immediates are treated as registers, fragment arithmetic
beyond MOV is not implemented, and texture sampler/view and blend handling are
stubs. Do not enable this build globally or use it to judge Plasma/KWin yet.
The original constant-color triangle fails despite correct context creation.
The final build returns exit 1 for this check without crashing; private softpipe
passes the same constant shaders (exit 2 indicates its software renderer).
The passing probe uses attribute colors and MOV shaders to test the implemented
drawing path. Those broader gaps have not been fixed by changing the probe.

Five tracked patches fix the Clang initializer, texture-format capability
reporting, null depth/disabled render-target relocations, the required
`sampler_view_release` callback, and an empty interpolation-instruction list
access in constant-only fragment compilation. GDB traced the teardown crash to a
null callback in `st_destroy_context`; Mesa's standard release helper fixes it.

## Building

```sh
bash scripts/build_mesa_grate.sh
```

This fetches the pinned source when absent, applies tracked patches, builds a
dedicated Docker image and an ARMv7 musl sysroot, and cross compiles on the host.
It does not install compilers on the tablet. The image uses the existing
`thinkpad-nura-build:2026-10-05` base. Alpine edge build dependencies may change;
retain the package/build logs and artifact hashes when comparing builds.

The cross file explicitly selects ARMv7-A, hard-float **VFPv3-D16**, and disables
NEON format optimizations with `NO_FORMAT_ASM`. The Cortex-A9 in this tablet has
no NEON. LLVM and LLVM drawing are disabled; the drivers are Grate and softpipe.
`legacy-x11=dri2` is explicitly enabled for opentegra Xorg. Its default disables
the hardware path on this DRI2-only X server and selects software instead.
The viewport patch replaces `powf(2.0f, -21)` with the identical constant
`0x1p-21f`, accepted by Clang in a static initializer.

Artifacts:

- `build/mesa-grate-armv7.tar.gz`: private install at `/opt/indigo-mesa/647c79415a02`.
- `build/gpu-pixel-check`: GBM/render-node GLES2 check with shader drawing and readback.
- `port/mesa/indigo-gpu-run`: process-local library/DRI selection wrapper.

The private install includes `share/indigo-build.json` recording the source
commit, source diff hash, patch hashes, cross-file hash and compiler version.

## Installing and checking on the tablet

Stage those three files plus `scripts/install_tablet_mesa.py` on the tablet.
Create `SHA256SUMS` with hashes and just the filenames of the three artifacts.
Validate that manifest against its host hash before installing. Run:

```sh
python3 /tmp/indigo-mesa-stage/install_tablet_mesa.py /tmp/indigo-mesa-stage
su julian -c 'timeout -s KILL 10 /usr/local/bin/indigo-gpu-run /usr/local/bin/gpu-pixel-check'
su julian -c 'DISPLAY=:0 XAUTHORITY=/home/julian/.Xauthority /usr/local/bin/indigo-gpu-run glxinfo -B'
```

The installer checks for root privileges and the external SD controller
`c8000400`, checks artifact hashes, and restricts extraction to the private
prefix. Distribution Mesa stays installed. Use absolute wrapper paths because
this tablet's `su` environment does not include `/usr/local/bin` in PATH.

The pixel check clears a texture blue, draws a red triangle using attribute-color
GLES2 shaders and a VBO, waits for drawing, and checks center and corner RGBA pixels.
Exit 0 requires correct pixels and renderer `Tegra`. Exit 2 means pixels are
correct but the renderer is software. Exit 1 indicates failure.
`--x11` additionally presents a 400x300 window for 20 seconds and verifies its
center pixel. `--benchmark --size=400x300` repeatedly clears/draws/finishes for
three seconds, then validates the final frame. It measures this implemented
workload, not general game or compositor performance.
`--constants` exercises the original literal-color shaders and exposes the
missing immediate support instead of avoiding it.

Bounded performance measurements use the same scenes as the earlier baseline:

```sh
python3 /tmp/measure_tablet_performance.py --phase graphics --private-mesa --output /tmp/indigo-grate.json
python3 /tmp/measure_tablet_performance.py --phase graphics --private-mesa --driver softpipe --output /tmp/indigo-private-softpipe.json
python3 /tmp/measure_tablet_performance.py --phase graphics --private-mesa --workload simple-triangle --output /tmp/indigo-simple-grate.json
python3 /tmp/measure_tablet_performance.py --phase graphics --private-mesa --workload simple-triangle --driver softpipe --output /tmp/indigo-simple-softpipe.json
```

Both standard glmark2 build/phong runs complete but report unimplemented shader
operations. Their FPS and scores are **invalid performance results**. The
measurement helper marks those results invalid. Renderer identity, correct
pixels and Grate's GR2D clear/GR3D draw submissions establish the narrower
hardware drawing result. It does not establish that other shaders, textures,
blending or Wayland work.

The simple verified hardware workload measured 1,434.54 FPS at 400x300 and
296.14 FPS at 800x1280, including clear, draw and completion each frame. Final
pixels pass at both sizes. These short synthetic runs do not predict Plasma
performance or establish sustained stability. Softpipe renders the identical
workload correctly at 39.82 FPS and 4.77 FPS respectively, approximately 36x and
62x slower. The hardware runs used 30.7% and 15.5% of the combined CPU capacity,
versus 55.5% and 56.2% for softpipe. Peak temperature was 34.25C for these runs,
with no swap use. The requested software renderer was verified from actual output.

Evidence under `diagnostics/`: `grate-experimental-channel-probe.txt`,
`grate-25-attribute-pixel.txt`, `grate-final-verification.txt`,
`grate-pixel-cleanup-backtrace.txt`, `indigo-grate.json`,
`indigo-simple-grate.json` and `indigo-simple-softpipe.json`.
`indigo-simple-softpipe-first.json` is an invalid selection attempt: it requested
softpipe but still used Grate. GBM needs `GBM_ALWAYS_SOFTWARE=1` as well as
`LIBGL_ALWAYS_SOFTWARE=1`; the helper now checks actual driver identity.

The distribution graphics stack and XFCE default are untouched. The old
`/opt/indigo-mesa/2a7bf9cc5eb1` candidate remains on SD; the wrapper selects
`/opt/indigo-mesa/647c79415a02`. For a process-local CPU fallback, use:

```sh
LIBGL_ALWAYS_SOFTWARE=1 GBM_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=softpipe /usr/local/bin/indigo-gpu-run YOUR_PROGRAM
```

These installs are on the live external SD. The earlier exported rootfs image
has not been regenerated with this build. Physical confirmation of the visible
test window remains pending; its framebuffer readback and presentation passed.
