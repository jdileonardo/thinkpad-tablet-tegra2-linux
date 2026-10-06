# Development workflow and internal installation

## Current checkpoint

The [XFCE stability and calendar check](xfce-stability.md) records five minutes
of idle samples and a real GTK3 calendar frame through the active display path.
Memory headroom is adequate for that small fixture. Longer operation, graphics
allocation lifetime and the actual service integrations remain unvalidated.

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

The current boot has three parts:

| Part | Location and role |
| --- | --- |
| U-Boot, kernel, device tree and bootstrap initramfs | Downloaded over USB APX into RAM on each development boot |
| Nura root filesystem, packages and configuration | Persist on the external SD card between boots |
| Stock Android and its boot layout | Remain on internal eMMC; unchanged by this port |

USB is also the diagnostic console. The SD card is not rewritten for each
kernel or graphics test. Normal userspace development changes persist there;
kernel changes require rebuilding the RAM payload and booting it again.

## Workflow for the next bring-up work

Keep RAM boot and the SD root while validating XFCE and its applications. This
allows kernel rollback without changing the internal bootloader and keeps
the working XFCE desktop available between reversible graphics trials.

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

Existing builders and trial runners cover much of this, but deployment and
evidence collection still involve manual steps. The next workflow improvements
are a command that ties those steps together, complete package/container
pinning, and a freshly built SD image containing the verified private GPU
components. The live development card currently contains additions that are
not yet included in the exported image.

## Eventual internal installation

On 2026-10-06 the user said they are willing to flash internal storage
eventually. No internal flash is part of this checkpoint. Internal installation
does not resolve outstanding graphics defects or validate application behavior.

First make the candidate reproducible on a fresh SD image and verify the
intended desktop, recovery path and repeated boots. Then inspect the tablet's
actual internal partition and boot layout and choose an installation method
based on that evidence. Do not apply the SD whole-disk image to internal eMMC:
the existing Tegra boot layout needs separate handling.

Moving the root filesystem to eMMC and making the tablet boot without a host
are separate changes. A possible intermediate step is an internal root
filesystem with the existing APX RAM boot. Whether to do that first or retain
SD while establishing persistent boot depends on the supported boot method;
that method has not been selected or verified yet. The current bootstrap
deliberately accepts only the external SD controller and UUID, so an internal
root requires an explicit new boot profile.

[PORTING.md](../PORTING.md#storage-preservation) records verified stock partition,
BCT and eMMC boot-region backups. They are not a full disk backup and restore
has not been tested. Before an internal write, confirm the eMMC identity,
target ranges, backup hashes and the APX recovery procedure, and use stable
dock power given the unverified battery. Preserve a known working SD/RAM
recovery setup through the transition.
