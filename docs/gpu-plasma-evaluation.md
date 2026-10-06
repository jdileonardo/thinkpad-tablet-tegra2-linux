# Native Wayland and Plasma graphics evaluation

The native display and hardware Wayland-client paths now pass on the physical
Indigo tablet. Plasma is not ready: KWin rejects a required missing extension,
and Qt Quick's chosen RGB565 rendering path produces incorrect pixels.
The kernel and private Mesa driver are unchanged from the
[nested compositor checkpoint](gpu-compositor.md).

## Results

| Check | Result and scope |
| --- | --- |
| Native Weston 16 DRM backend | Starts with GBM, atomic modesetting and the Grate/Tegra GLES 2 renderer on DPI-1 |
| Hardware Wayland EGL client, 32-bit buffers | Three changing frames, six local GPU samples and an independent full scanout capture pass |
| Hardware drawing in that client | Orthographic matrices, four- and two-component vertex attributes, triangle strips and 16-bit indexed triangles pass |
| Qt Quick software client through GPU Weston | Final opaque pattern passes with normal output and, after settling, rotate-90 output |
| Qt Quick software client through Pixman Weston | Rotated final pattern passes; its complete RGB capture matches the hardware EGL client |
| Qt Quick OpenGL client | Creates a Grate/Tegra GLES 2 context, but its final pattern fails with the RGB565 buffers it selects |
| Isolated RGB565 client | Both a shader-drawn quad and a scissored clear fail their first local GPU sample; blue remains where red is expected, with no GL error |
| KWin 6.7.5 | Reaches EGL/context creation but rejects the rendering context; its GLES extension gate requires missing 3D-texture support |

The rotated passing captures are 1280x800 physical scanouts of 800x1280 logical
surfaces. They contain exactly 512,000 blue and 512,000 red pixels, with identical
RGB bytes across the EGL clear, EGL drawing, Pixman Qt reference and settled
software Qt client through GPU Weston. The normal software Qt capture has the
same colors in the expected left/right layout.

Capture comparisons, source/build identities and raw logs are in
[gpu-plasma-checkpoint.json](gpu-plasma-checkpoint.json) and
[the evidence directory](evidence/grate-20261006-plasma).
Reviewable logs have terminal escapes/trailing whitespace removed. The raw
archives preserve original bytes; the tablet manifest's hashes refer to those
archive contents, while the checkpoint hashes identify the reviewable files.

## KWin's current blocker

The installed package is `kwin-6.7.5-r1`, using Qt 6.11.1. Its
[GLES support check](https://github.com/KDE/kwin/blob/v6.7.5/src/opengl/eglcontext.cpp#L489)
requires GLES 3 or `GL_OES_texture_3D`, alongside shader, framebuffer, unpack
and BGRA-read capabilities. Our actual GBM context reports Grate/Tegra,
GLES 2.0 and the unpack/BGRA extensions, but no `GL_OES_texture_3D`.
The current driver explicitly sets `max_texture_3d_levels = 0`.

This is a concrete necessary capability gap. It does not establish that
passing the extension gate would make KWin's shader gate or full compositor
work. Implement and verify the API before advertising it, or audit an honest
KWin compatibility path that makes unsupported functionality optional.
Simply removing the startup check is not validated by these experiments.

Both `KWIN_COMPOSE=O2ES` and `O2` attempts reject the context; the distribution
Qt build still requests its GLES path. These are not proof of an independently
tested desktop OpenGL alternative. A private softpipe KWin attempt fails
earlier during DRM-device discovery, so it provides no successful KWin
software baseline. Native KWin and the Plasma Mobile shell remain untested.

## Qt Quick and RGB565

The fixture uses Qt Quick's OpenGL RHI with the basic render loop, animated
geometry, text and a final static pattern. Logs identify vendor Grate, renderer
Tegra and GLES 2.0. Qt chooses 16-bit RGB565 buffers: Wayland DMA-BUF messages
show format `0x36314752`, 1280x800 and pitch 2560 in the normal-output trial.
The actual scanout remains entirely blue instead of the expected red/blue
halves, including a repeat with two seconds of settling time.

The small EGL client reproduces an RGB565 failure independently of Qt. Its
32-bit matrix/drawing variant passes, while the 16-bit variant reads blue
where it drew red. The scissored-clear variant fails similarly. That clear
can itself use a drawing fallback, so this does not establish that every
RGB565 operation is broken. The exact faulty hardware state is not yet known.

The earlier all-red rotated Qt hardware capture is also retained. Its
relationship to RGB565 rendering and texture sampling has not been proved.
Fix or accurately restrict the unsupported render-target path, then repeat
Qt's OpenGL test with verified buffer identities and actual output. Animation,
text and transparency are exercised but their intermediate pixels are not
validated by the final static capture.

## Timing and instrumentation failures

Qt's `frameSwapped` marker precedes the compositor's final displayed frame.
An immediate software Qt capture retained part of the animation. It passes
after a two-second compositor settling interval; this is not evidence of a
rotation defect. The runner now waits before reading scanout.

The first normal hardware Qt capture was unsupported by the probe because
Qt's direct scanout used RGB565. The probe now decodes linear RGB565/BGR565
and RGB/BGR 8888 buffers. A fresh capture confirmed the actual incorrect blue
image. That initial capture-tool error is not counted as a driver failure.

The first native trial used an unsupported seatd socket option; it restored
XFCE and produced no graphics result. The corrected runner uses an owned
seatd process and refuses to replace an existing socket.

## Reproduction and recovery

Install `kwin`, `qt6-qtdeclarative`, `weston-backend-drm` and `seatd` on the
verified development SD root. The package transaction also runs Nura's SD
`mkinitfs`/`boot-deploy` triggers; those files do not replace the host's current
RAM payload. Package additions are not yet integrated into the exported image.

```sh
bash scripts/build_graphics_stack_probes.sh
```

This reuses the SDK/container prepared by `build_opentegra.sh`, without a
package refresh. Stage the generated `graphics-stack-check` and
`wayland-egl-check` executables under `/tmp`, together with the tracked QML
fixture as `/tmp/qt-wayland-scenegraph-check.qml` and the native trial runner.
Verify their SHA256 values from `build/graphics-stack-probes.json` before use.

Run as root from the tablet diagnostic console, after ending any DRI3 trial:

```sh
python3 /tmp/tablet-native-weston-trial.py --label fresh-egl --egl-client --egl-draw
python3 /tmp/tablet-native-weston-trial.py --label fresh-qt-reference --qml-client --qml-software
python3 /tmp/tablet-native-weston-trial.py --label fresh-qt-gl --qml-client --transform normal
python3 /tmp/tablet-native-weston-trial.py --label fresh-rgb565 --egl-client --egl-draw --egl-rgb565 --transform normal
```

Use fresh labels. The last two commands currently fail pixel validation.
Each run records logs and captures, stops LightDM temporarily, and restores
XFCE in `finally`. An independent 90-second watchdog also restores it if
the runner dies or hangs. A failed pixel check remains a failed trial.
USB console/transfer scripts now take an exclusive terminal lock to reject
overlapping readers. Their lock exclusion/release was checked on a PTY, and
ordinary device transfers/readouts work with the lock.

## Remaining work

Prioritize the reproduced RGB565 rendering failure, then KWin's 3D-texture
requirement and shader compatibility. Follow with native KWin, accelerated
Qt/Plasma, sustained frame swaps, meaningful performance measurements and
Wayland input/rotation integration. Existing client-array and intermittent
NPOT/stale-frame issues remain open.

These are bounded functional checks, not an FPS or long-term stability test.
Kernel taint stays 12288, with no new bad-page or GPU-hang messages in the
captured log. Earlier 132 MB allocation failures from Xorg remain in the log.
The restored desktop had 1,632 KiB `CmaFree` at an earlier check and 4,268 KiB
after the final trial. Only Xorg remains in DRM's active-client list. The cause
and allocation lifetime still need investigation; these counts alone do not
prove a leak.
Weston's layer-finalization/pending-flip shutdown warnings remain open.

XFCE and its distribution Xorg driver are restored, with 800x1280 left
rotation and network traffic working. Fresh physical touch/rotation confirmation
is pending. Pen batteries, battery reporting, full build-input pinning and
fresh SD-image integration remain the previously agreed follow-ups.
