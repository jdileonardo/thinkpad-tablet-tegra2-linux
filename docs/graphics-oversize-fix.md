# Large-pixmap allocation fallback, 2026-10-06

The longer observation of the installed scanout-reference fix caught the
historical 132,710,400-byte allocation burst again. XFCE/Xorg survived and all
120 Wi-Fi checks passed over 1,800 seconds, but the kernel logged three failed
allocations and Xorg's global cache-drop retry. The [observation summary](evidence/image-20261006/installed-desktop-observation.json)
records this as an unsuccessful clean-graphics run, not a stable image release.

## Reproduction and fix

A bounded Xlib probe creates 640×640 and 5760×5760 ordinary pixmaps, draws
colored rectangles at opposite corners, and reads back every pixel in those
rectangles. Both sizes pass 2,048 pixel checks before the fix. The
[userspace/kernel trace](evidence/image-20261006/oversize-before-trace.txt)
proves that the large pixmap has 32-bit storage and causes three
132,710,400-byte GEM requests with flags `0x20`; every request returns `-ENOMEM`.
The kernel reports the same allocation/cache-drop pattern as the idle incident.
Rendering already succeeds through the existing system-memory fallback.

[Patch 4](../port/opentegra/0004-use-sysmem-for-pixmaps-larger-than-cma.patch)
reads the boot's CMA capacity once and bypasses BO allocation for ordinary
pixmaps exceeding that capacity when the driver has no IOMMU. On this tablet
the capacity is 64 MiB; the request is 126.56 MiB, and the kernel's buddy
allocator maximum order is 10. It therefore goes directly to the existing
CPU fallback. Unknown/zero CMA capacity, IOMMU operation and DRI pixmaps keep
their existing behavior. CMA capacity is an allocation policy bound here,
not a claim about currently free CMA pages.

The [after trace](evidence/image-20261006/oversize-after-trace.txt) records both
pixmap creations and **no large GEM attempts**. Both sizes still pass all
2,048 checks, with no cache drop or new kernel errors. The
[comparison](evidence/image-20261006/oversize-comparison.json) records module
identity and zero trace overruns/dropped events. The selected module SHA256 is:

```text
61e6191a7492e63c9d2fe79f9dade2cd71c1b286b1f4dceac4631250a9a3bba7
```

The original background client's identity and exact geometry remain unknown.
This reproduces and fixes the ordinary-pixmap allocation path for the same
request size; it does not establish the original client's identity or cover
all possible DRI allocation failures.

## Regression checks and limits

Two complete rotation circuits plus calendar open/close ran under the candidate
with automatic driver rollback. There were no GEM creation or mapping errors,
CMA errors, new kernel messages or lost trace events. The first short settling
period retained 14 MiB of new live/cached reservations; the second used a
60-second settling period, released 19.8125 MiB against 19.25 MiB of new
allocation, and ended with 25.035 MiB of unreserved CMA. This is consistent
with the driver's activity-driven BO cache, which retains small bucket lists
for up to 60 seconds; it is not evidence of indefinitely zero cache use.
The [first](evidence/image-20261006/oversize-rotation-summary.json) and
[repeat](evidence/image-20261006/oversize-rotation-repeat-summary.json) summaries
retain the complete accounting.

After waking the idle-blanked display, the [calendar comparison](evidence/image-20261006/oversize-calendar-awake-comparison.json)
matches all **421,600 client pixels** to the actual rotated scanout. An earlier
capture was entirely black while the five-minute idle blanker was active and
did not pass; only the awake comparison is counted. The images contain the
synthetic calendar fixture, not a user's calendar service.

The fixed driver is selected for XFCE and included in the
[corrected SD image](xfce-image.md). Fresh-image boots, longer sustained use,
physical input confirmation and service integrations remain required. RGB565,
KWin/3D textures and source-build Tegra114 shader reproducibility retain their
previous limits. No internal storage was written.

## Repetition

Build `port/opentegra/oversize-pixmap-check.c` against the frozen ARM SDK and
Xlib. Run it as `julian` with the live X display/authentication. Use
`scripts/tablet_oversize_trace.py` as root with a fresh `/tmp` output directory
for 10–300 seconds. It parses the exact ARM32 module symbol, creates a private
trace instance with userspace creation and kernel allocation probes, and removes
them on exit or through its bounded watchdog. ARM Thumb uprobes are explicitly
rejected because this kernel's ARM uprobes do not support them.
