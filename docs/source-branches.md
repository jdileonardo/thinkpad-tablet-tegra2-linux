# Upstream source branches and image readiness

The port has local branches in the original kernel, Xorg DDX and candidate
Mesa Git repositories. They retain the pinned upstream commit as their base.
The existing build checkouts remain on those bases with the recorded patches
applied; their HEADs and real Git indexes were not changed by the export.

| Repository | Local branch | Port commits |
| --- | --- | --- |
| `sources/linux-nura` | `indigo/xfce-bringup` | 3: panel, DMA-BUF synchronization, board DTS/Makefile |
| `sources/xf86-video-opentegra` | `indigo/xfce-bringup` | 4: DRI3/build compatibility, DMA-BUF export access, scanout reference fix, oversized-pixmap fallback |
| `sources/mesa-grate-ad06de32d309` | `indigo/xfce-bringup` | 16: the recorded candidate patch series |

[The branch manifest](source-branches-checkpoint.json) records base/tip commits,
tree identities and exported patch hashes. These are local commits; no upstream
submission or remote push has been performed. Packaging a change as a commit
does not certify every affected rendering path or establish upstream acceptance.
The Mesa series includes diagnostic changes; curate those separately from
production fixes before submitting it upstream.

Recreate/advance the exports with:

```sh
python3 scripts/export_source_branches.py
```

The exporter uses disposable Git indexes, checks that each final tree exactly
matches the build checkout, then creates commits and writes `git format-patch`
series under `build/source-exports/`. An existing branch may advance only from
a matching recorded patch prefix; unrelated branch changes cause refusal.
The kernel board files are exported as the third commit. Keep using the main
repo's patch files as the input to the current builders. A separate worktree
on an exported branch can be used for reviewing or preparing submissions.

## Readiness for the selected XFCE workload

The target is a docked XFCE desktop. Physical touch,
user-confirmed rotation and Wi-Fi work; small GTK calendar rendering and several
hardware 3D/compositor paths have measured device evidence. This is a useful
development system, not yet a validated daily-use image.

Before an image is selected as the working baseline:

1. Extend the [validated rotation-buffer reference fix](graphics-rotation-fix.md)
   to longer operation and fresh-image boot. Two circuits, allocation/free
   records and actual calendar display pixels now pass. The old large
   allocation requests remain a separate unresolved issue unless reproduced
   and explained. The [oversized-pixmap follow-up](graphics-oversize-fix.md)
   now reproduces the same request size through ordinary X pixmaps and avoids
   the failed GEM/cache-drop path. The original background client is unidentified.
2. The [new image recipe](xfce-image.md) packages the selected DDX/Mesa
   components and desktop configuration from frozen build artifacts and the
   cached distribution rootfs. Container IDs and rootfs/SDK inputs are pinned
   for offline assembly. A fully source-rebuilt release remains separate work.
3. Boot a freshly built SD image repeatedly and exercise the intended workload
   for hours, checking memory growth, display, touch/rotation, Wi-Fi and recovery.
4. Verify the intended desktop applications on the tablet.

RGB565 rendering and KWin's missing 3D-texture capability remain defects or
unsupported capabilities; they are not prerequisites for the verified GTK/XFCE
path. Do not describe the driver as generally complete or enable it for arbitrary
applications without checking their required formats/features. Pen and battery
testing remain deferred under the user's existing constraints.

`scripts/create_nura_sd_image.py` now assembles and checks an external-SD
image containing the selected graphics additions and desktop configuration.
SD image production and internal installation are distinct: the SD bootstrap
selects the external controller/UUID. The subsequent
[internal installation](internal-install.md) added an internal bootstrap,
persistent U-Boot and a clean eMMC layout, with full write/readback and normal
ROM boot checks. Physical cold power-on with the card removed remains pending.
The SD whole-disk image must not be used unchanged as an internal install image.
See [build, copy, flash and upstream preparation](build-copy-flash.md) for the
repeatable commands and remaining installer/source-bootstrap limitations.

The exported kernel branch does not include the out-of-tree N-Trig module.
U-Boot changes and Nura device packaging also need separate submission work.
These exported branches preserve our working source changes; their commit
descriptions, sign-offs and target-tree compatibility still need review before
upstream submission.
