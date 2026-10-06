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

## Reuse candidates found after bring-up

A follow-up source audit on 2026-10-05 found a substantially more developed
Libre Tegra branch, `grate-tmp`, at
`ad06de32d309506c48e4169a15f56e2f95e9712d`. Its `fp/nir.c` and `vp/nir.c`
implement NIR shader translation, with fragment arithmetic beyond MOV and
embedded constants. `grate_program.c` includes vertex immediate upload;
`grate_state.c` includes sampler/view tracking and texture descriptor emission.
Its blend-state handler still explicitly leaves rendering opaque, and the
texture code records unresolved mipmap behavior.

The branch was initially a **source-inspected reuse candidate**; the subsequent
physical-device results are recorded below.
The earlier assessment of substantial missing implementation applies to the
installed `grate-25.1.9` branch; it does not establish that those implementations
must be written from scratch. Evaluate the newer branch's build and kernel ABI,
then repeat exact pixel tests before selecting it or transplanting its code.
Keep the known working build as a reference during that evaluation.

The original GitHub `grate` and `22.2.4` branches still have MOV-only fragment
TGSI translation and sampler/blend stubs. Libre Tegra's
`grate-wip-conversion` and `grate-wip-vertex-nir` also retain MOV-only fragment
TGSI translation at the inspected heads. This was a targeted source comparison,
not a complete audit of every historical commit or a stability assessment.
Downloaded source snapshots are under `diagnostics/gpu-audit-*`.

The current source candidate is at
https://codeberg.org/libre-tegra/mesa/src/commit/ad06de32d309506c48e4169a15f56e2f95e9712d/src/gallium/drivers/grate.

## Candidate bring-up results

The pinned NIR candidate is now built and installed separately at
`/opt/indigo-mesa/ad06de32d309`. Both builds remain on the external SD.
The wrapper still selects the reference unless `INDIGO_MESA_REVISION` explicitly
selects the candidate. Distribution Mesa and XFCE's default have not changed.

The candidate also expected upstream Tegra's newer channel API. A tracked
Tegra20-only adapter uses the existing legacy OPEN_CHANNEL, GET_SYNCPT, SUBMIT
and SYNCPT_WAIT ioctls. It retains the candidate's shader compiler and render
state, translates buffer relocations to GEM handles, prepends the channel class,
and converts nanosecond waits to the legacy millisecond unit. The kernel remains
`7.0.1-nura-indigo-ram`; its age is not the cause of the interface mismatch.
The Clang viewport constant fix is included with this adapter.

Physical checks pass for attribute colors, literal shader constants, uniforms,
and multiply/add arithmetic. The strengthened arithmetic check expects
approximately `128,64,191,255`, different from its input red attribute; hardware
reads `127,64,191,255`, software `128,64,191,255`.

Four-quadrant nearest-neighbor texture checks pass for 3, 4, 8, 16, 17 and 32
pixel square textures. Initially, 2x2 RGBA returned correct row-zero colors but
zeroes for row one. Raising the tiny power-of-two RGBA row stride from 8 to 16
bytes on Tegra20 fixes all four samples; 4x4 and 17x17 checks still pass. The
tracked patch also pads corresponding mip storage, but mip sampling is not
validated and the candidate deliberately restricts sampling to level zero.

The candidate's own `fptest`, `quadtest`, `vstest` and `blendtest` are cross
compiled from the pinned source and compared on the tablet against its softpipe
build. All processes exit cleanly, which alone is not a correctness verdict:

- Initial `fptest`: 241 of 331 RGBA samples agreed within 10 channel levels.
  The 90 failures belonged to ten special-function cases. The SFU extension
  and its conservative sequencing workaround are recorded below.
- `quadtest`: all nine textured-quad samples match software exactly.
- `vstest`: both renderers place the transformed quad at x=24..55, with no GL error.
- `blendtest`: hardware writes opaque red; software produces the expected
  red/blue mix. The independent alpha check also fails on hardware and passes
  on software. Blending is still a concrete compositor blocker.

Do not promote this candidate to system Mesa yet. Next work is the unsupported
remaining shader coverage and blending, followed by X11/Wayland compositor validation,
stability checks and integration into the reproducible OS image. This is a
substantial reuse milestone, not completed GPU support or GLES conformance.

```sh
bash scripts/build_mesa_grate.sh candidate
# After staging and checking the candidate artifact manifest on the tablet:
python3 /tmp/indigo-mesa-candidate/install_tablet_mesa.py /tmp/indigo-mesa-candidate --revision ad06de32d309
su julian -c 'INDIGO_MESA_REVISION=ad06de32d309 /usr/local/bin/indigo-gpu-run /usr/local/bin/gpu-pixel-check --texture'
```

Add `--constants`, `--uniforms`, `--arithmetic`, `--blend`, or
`--texture --texture-size=17` to exercise individual paths. Correct hardware
pixels exit 0, correct software pixels exit 2, and mismatches exit 1.

Evidence: `diagnostics/grate-nir-install-first-pixel.txt`,
`grate-nir-feature-pixels.txt`, `grate-nir-texture-sweep.txt`,
`grate-nir-row-fix-verification.txt`, `grate-nir-upstream-tests.txt`,
`indigo-nir-{hardware,software}-{fptest,quadtest,vstest,blendtest}.log`, and
`indigo-nir-fptest-comparison.json`. Earlier arithmetic output is superseded by
the strengthened differently-colored check in the texture sweep.

## Fragment special-function checkpoint

Two further candidate patches implement NIR fraction, floor, reciprocal,
reciprocal square root and square root using the existing Grate MFU encoding.
Floor uses `x - fract(x)` and preserves its input in a temporary. An ALU move
feeds a scratch row in one instruction, then MFU applies the operation and the
ALU retains the result. This reuses the ISA and assembler examples from
`grate-driver/grate`, pinned in `sources.lock.json` at
`ce8c4d2c62880ee5ffab90fd5f4c0554d4dbcc6d`.

With the original output window (MAX_OUT=300, MIN_OUT=200), the new compiler
passes 265/331 samples, with 66 incorrect special-function samples. Routing the
SFU result through its multiplier, changing the DW instruction count and
turning off ALLOW_QID_COLLISIONS all produced byte-identical test output.
The intended window of 32/16 passed 283/331; the intended single-quad window
of 4/4 passed 331/331. The later command-width audit below found that the IMM
write truncated MIN_OUT, so these earlier experiments actually used minimum
zero. They support a sequencing/feedback problem with work in flight, but do
not establish the underlying hardware requirement.

Patch 0004 applies 4/4 to Tegra20 shaders with multiple pipeline instructions
or SFU work beyond the ordinary RCP R4 interpolation setup. An offset-only
shader in the isolation harness exposed the same feedback problem without an
SFU, so limiting only special-function shaders was insufficient. Each draw
programs its shader's window;
MAX_QID uses the same window when the fragment program is compiled. Other
shaders retain 300/200. This is a conservative correctness workaround.
Its throughput for affected shaders has not been measured, and larger-window scheduling still
needs investigation. Passing this harness is not complete GLES conformance.

The reusable comparison checks renderer identity, all 331 expected samples,
missing/duplicate samples, GL errors and unsupported/compiler diagnostics:

```sh
python3 scripts/compare_grate_fptest.py diagnostics/indigo-nir-multipass-final-1.log diagnostics/indigo-nir-sfu-checkpoint-software.log --expected-samples 367 --output diagnostics/indigo-nir-multipass-final-1-comparison.json
```

Scheduling evidence and SHA256 hashes are retained in
`diagnostics/grate-sfu-scheduling-experiments.json`, with the corresponding
`indigo-nir-sfu-*.log` and comparison JSON files. The builder also produces
`bin/fptest-sfu-isolation` by applying the tracked
`port/mesa/tests/sfu-isolation.patch` to the pinned upstream harness. It adds
offset and uniform-fed SFU cases (367 total samples). Its patch hash is recorded
in the installed build metadata. An early run using a globally serialized window
passed 366/367: one `tex_500@0` sample had an incorrect texture color. Retain
this as a possible texture/cache stability issue when broadening validation.
The same texture sample failed in one of three later 331-sample runs; the other
two runs passed 331/331. All 90 special-function samples passed those runs.
The final scoped workaround passed 367/367 twice and 366/367 once across
three expanded runs. The remaining mismatch was `tex_500@1`; shader cases
passed every run. The intermittent NPOT texture problem remains open. Native
800x1280 attribute-triangle drawing passed at 182.83 FPS (549 frames in
3.002751 seconds); this is not an affected-shader or compositor benchmark.
`docs/gpu-sfu-checkpoint.json` retains the source/patch/artifact/log hashes,
sample counts and failed pixels in Git. Raw logs remain under `diagnostics/`.
Blending, compositor validation and OS-image integration remain unfinished.

## Sequencer command width, allocation and desktop follow-up

Patch 0008 fixes an actual command-encoding error: `host1x_opcode_imm` takes a
16-bit value while PSEQ_CTL.MIN_OUT starts at bit 14. MIN_OUT=200 and even
MIN_OUT=4 were truncated to zero. The control is now written with an INCR
command and a full 32-bit payload. With the corrected write, ten conservative
367-sample runs pass completely. Ten runs with the original 300/200 concurrency
fail 89 samples each; the single-quad workaround is still required.

Two cache investigations retain complete output in `docs/evidence/grate-20261006`:
30 isolated texture runs per cache setting (270 samples each), and 20 full
runs per setting (7,340 samples each). All passed with the cache enabled and
disabled. This does not explain or resolve the previously observed intermittent
NPOT corruption; do not claim a cache fix from the absence of a new failure.
Patch 0005 adds an opt-in cache-disable control for further investigation.

A native-window trial revealed contiguous-memory pressure: allocation of a
5,636,096-byte texture failed with GL_OUT_OF_MEMORY while hundreds of MB of
ordinary RAM remained available. The kernel reserves only 64 MiB of CMA;
11,732 KiB was free at one observation and 7,392 KiB before the GART trial.
The running kernel already supports Tegra20 GART and sparse GEM objects in
its legacy job interface. Patch 0009 reuses that support for off-screen
resources of at least 1 MiB, using the experimental ABI's SPARSE flag (bit 4).
SCANOUT, DISPLAY_TARGET and SHARED resources retain their allocation path.
Three opt-in trials and three final default runs pass all 367 samples under
that pressure, with no GL errors. Large shared/display allocations still need
separate validation. The final native triangle check passes at 188.82 FPS
(567 frames in 3.002851 seconds); this remains a short synthetic workload.
The matrix and nine textured-quad checks still match their software references.

Candidate X11/EGL presentation displays and reads back correct pixels, but
reports `softpipe` and exit 2. Candidate GLX also reports softpipe and
`Accelerated: no`. These are software results. Source inspection confirms that
Mesa 26's EGL/GLX paths only implement DRI3 hardware presentation, whereas the
current opentegra X server supplies DRI2. Restore a compatible legacy path or
add DRI3 support to the X driver; modern DRM/GBM Wayland presentation is another
path that needs physical validation. No hardware compositor has been verified.

Patches 0006/0007 provide process-local destination-read diagnostics: raw PSEQ
instruction upload with a copy epilogue and READ_DEST control. Tested LD,
LD_R20 and LD_R80 words, with the sequencer count adjusted for the epilogue,
did not reproduce the cleared destination color. One LD_R20 trial changed the
result to zero, but that does not establish a usable framebuffer fetch.
The normal alpha test still writes red instead of the expected red/blue mix.
Blending remains unimplemented. These diagnostics are off by default.

The patch applier now validates the whole stack through a disposable Git index
and accepts only a known stack prefix. It preserves unrecorded source edits by
refusing to build them. Checking each earlier patch individually in reverse
failed when later patches modified its context, despite the complete stack
being correct. Both the five-patch reference and nine-patch candidate validate.
`docs/gpu-integration-checkpoint.json` records the final source/build/artifact
hashes and results. System Mesa, XFCE, touch configuration, Wi-Fi and SD boot
have not been replaced by these process-local trials. The goal remains open:
blending, native presentation, compositor/stability validation and exported
image integration are still required.

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
For the Mesa 25 reference, `legacy-x11=dri2` enables its DRI2 path on
opentegra Xorg. The Mesa 26 candidate removed EGL/GLX DRI2 implementations;
its `legacy-x11` option is deprecated with no supported choices and no effect.
The builder now applies that option only when the source implements DRI2 and
records `x11_dri2: false` for the candidate. See the native-window results below.
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
