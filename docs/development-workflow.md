# Development workflow and internal installation

The [build, copy, flash and upstream guide](build-copy-flash.md) consolidates
the current recipes, frozen inputs and remaining release/submission work.

## Current checkpoint

The [XFCE stability and calendar check](xfce-stability.md) records five minutes
of idle samples and a real GTK3 calendar frame through the active display path.
Normal RAM headroom is adequate for that small fixture. The follow-up
[graphics allocation check](graphics-memory.md) finds inexpensive calendar
cycling but retained rotation buffers and actual CMA shortages with successful
allocation fallback. The subsequent [scanout reference fix](graphics-rotation-fix.md)
releases those buffers in two bounded tablet trials and is selected for XFCE.
The [large-pixmap fix](graphics-oversize-fix.md) follows a recurrence during
the half-hour observation: ordinary oversized pixmaps now use system memory
directly, avoiding failed contiguous requests and their cache-drop retry.
The [XFCE SD image checkpoint](xfce-image.md) packages the selected components
and frozen build inputs. Two physical boots of the new SD image and its input,
network and graphics checks have passed; the actual service integrations
remain unvalidated.

The [native Wayland evaluation](gpu-plasma-evaluation.md) verifies direct display
and hardware Wayland clients using 32-bit buffers. RGB565 rendering and KWin's
3D-texture requirement are current blockers; Plasma/KWin remain unvalidated.
The ordinary XFCE configuration is the intended desktop and the recovery path.

## Desktop target and priorities

On 2026-10-06 the user chose to focus on XFCE. The intended docked workload is
displaying a calendar and eventually controlling Spotify playback. Application
choices, calendar source and the Spotify playback device remain undecided.
Local Spotify audio playback is not currently a requirement.

Prioritize the working XFCE session on the tablet's approximately 1 GB of RAM:

1. Establish an idle memory/CPU baseline and check sustained desktop operation,
   touch, rotation and Wi-Fi. Investigate the observed Xorg CMA allocation
   failures before claiming long-term graphics stability.
2. Integrate the verified system into a reproducible SD image. Experimental
   graphics installations and packages should be included only when they are
   needed and validated for the intended workload.
3. Select and test calendar and Spotify-control applications against the actual
   services, measuring responsiveness and memory pressure on the tablet.
4. Configure reliable startup into the selected display/controller workflow,
   then evaluate host-independent boot and eventual internal installation.

Plasma, KWin's 3D-texture requirement and native Wayland integration are deferred.
Continue GPU work where it improves XFCE or the chosen applications; RGB565 and
other reproduced driver defects remain documented rather than prerequisites
for this desktop target. Battery reporting and pen testing remain follow-ups
under the user's existing docked-use and pen-battery constraints.

The [internal installation](internal-install.md) now supplies the normal boot
path. The bootloader is persistent, and kernel updates use replaceable extlinux
files rather than requiring a new bootloader flash.

The subsequent [CPU/backlight bring-up](power-bringup.md) adds an incremental
custom-kernel cpufreq module to the live internal installation. Automatic
scaling and module autoload pass ordinary reboot. This module is not yet in
the frozen image; keep its build/install recipe with the next image work.
Use standard `/sbin/reboot` so init runs the OpenRC shutdown path. Its latest
restart mounted internal ext4 without journal recovery, unlike the older
forced restart procedure.

| Part | Location and role |
| --- | --- |
| Board BCT and U-Boot | Internal eMMC hardware boot0, protected after installation |
| Kernel, device tree, bootstrap initramfs and extlinux configuration | `/boot` on the internal Linux root |
| Nura root filesystem, packages and configuration | Internal eMMC, expanded to its available capacity |
| Recovery root | Original working SD; its automatic extlinux entry is saved under a recovery filename |

USB remains the diagnostic console. The known-good APX/SD RAM payload starts
the recovery root without consulting its disabled extlinux entry. A separate
APX/internal-root payload has been built, but has not yet been tested on hardware.

## Workflow for the next bring-up work

The [source branch checkpoint](source-branches.md) exports the recorded patches
as local commits in the kernel, Xorg DDX and candidate Mesa repositories without
switching their build checkouts. It also lists the remaining image release checks.

Keep the APX payload, board BCT and working SD recovery root while developing
on internal storage. Userspace changes persist on eMMC. For kernel trials,
retain the installed known-good kernel/initramfs/DTB and use versioned filenames
in extlinux; the bootloader does not need reflashing. Match modules to each
candidate kernel. APX can still load a diagnostic or trial kernel into RAM.
The existing SD recovery payload is the hardware-tested recovery path.

1. Keep source changes and patches in Git. Record source revisions, artifact
   hashes and hardware evidence with each meaningful checkpoint.
2. Build only the changed components. Retain the previous working payload and
   private graphics installation before deploying a candidate.
3. Use the network for bulk userspace transfers when available; keep the USB
   console for recovery. Serialize console operations: one host reader at a time.
4. Use bounded graphics trials with automatic restoration. Check renderer
   identity, visible output and kernel logs before promoting a candidate.
5. Recheck touch, rotation and Wi-Fi after kernel or display changes. Input
   enumeration alone does not replace physical confirmation.

Deployment and evidence collection still involve manual steps. The new image
includes the selected private graphics components and desktop configuration,
and pins its binary inputs and container IDs. Mesa/Xorg rebuilds verify the
frozen SDK and skip dependency refresh by default. Fresh-card boot has passed;
long-duration reliability remains unmeasured, and the user cancelled the
additional 30-minute observation. Reproducibility from entirely rebuilt source
inputs remains distinct from this offline assembly checkpoint.

## Internal installation and recovery

The user authorized a clean Linux installation; cache, userdata and returning
to Android are not requirements. The [installation record](internal-install.md)
contains exact images, write bounds, checksums and physical boot results.
The [readiness audit](internal-install-readiness.md) retains original backups
and records the board BCT and eMMC identity. No additional MMC boot-configuration
change was required.

The SD-first bootloader falls through to internal eMMC because the SD's
`/boot/extlinux/extlinux.conf` was renamed to `extlinux.conf.sd-recovery`.
To restore automatic SD boot, start the known-good APX/SD payload and restore
that filename. Keep its original controller/UUID bootstrap on the SD.

Normal ROM restarts have been tested without an APX download. Physical card
removal and cold power-on still need the user's check. Use dock power given
the unverified battery. Original Android backups remain useful porting and
recovery material; a full stock restore has not been tested.
