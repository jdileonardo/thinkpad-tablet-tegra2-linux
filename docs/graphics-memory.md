# XFCE graphics allocation checkpoint

The follow-up [rotation reference fix](graphics-rotation-fix.md) identifies and
fixes the DDX scanout reference handoff, verifies release in two tablet trials,
and selects the fixed module for XFCE. The observations below describe the
earlier unpatched configuration.

Measured on the physical Indigo tablet on 2026-10-06, with kernel
`7.0.1-nura-indigo-ram`, the external SD root, and the installed distribution
`xf86-video-opentegra-0.6.0_git20211025-r1`. Xorg PID 29643 and XFCE session
PID 29667 stayed running throughout. No driver replacement, CMA resize, cache
drop or display-manager restart was performed by these diagnostic tools.

## Findings

**Calendar cycling is inexpensive; rotation retains large buffers and causes
real CMA allocation pressure.** These are separate observations from the old
132,710,400-byte allocation failures, which were not reproduced here.

`CmaFree` counts immediately free pages in the CMA region. Movable ordinary
pages can occupy that region without reserving graphics buffers. It is therefore
insufficient evidence of graphics exhaustion. The kernel's `cma_alloc_start`
trace exposes `available_count`, the unreserved CMA bitmap space. This is a
better measure of reservation pressure, but still does not guarantee that
migration and alignment will permit a particular contiguous allocation.
The region contains 16,384 4 KiB pages, or 64 MiB. The page size was confirmed
with `getconf PAGESIZE`; Xorg reports a 24 MiB EXA pool.

| Trial | Unreserved CMA range | End | Net CMA reservation change | GEM create failures |
| --- | --- | --- | --- | --- |
| Desktop reload, six calendar open/close cycles, settling | 19.60–21.91 MiB | 20.91 MiB | +1.00 MiB | 0 of 20 |
| Full rotation circuit, one calendar cycle, 10 s settling | 1.81–21.91 MiB | 4.00 MiB | +17.91 MiB | 0 of 43 |
| Three later calendar cycles, 75 s settling | 3.37–5.25 MiB | 5.00 MiB | +0.25 MiB | 0 of 18 |
| Second rotation circuit, one calendar cycle, 10 s settling | 1.75–5.50 MiB | 4.12 MiB | +1.13 MiB | 0 of 33 |

The first calendar trial allocated 3.31 MiB and released 2.31 MiB through CMA.
Its new GEM requests were only 64 KiB and 256 KiB. The net 1 MiB retention is
consistent with pool/cache warmup, but the trace alone does not classify its
userspace owners or establish a leak-free lifetime for every object.

Each rotation circuit requested **four new 4 MiB GEM buffers**. All four were
still live or cached at the end of that circuit's trace. No free of the first
circuit's four buffer addresses was observed in either later trace. There are
gaps between traces, so this is not a continuous lifetime record. The later
calendar activity and settling did not restore the earlier approximately
21 MiB CMA headroom. The second circuit also created four new large buffers;
it did not simply reuse the first circuit's buffers through the observed kernel
allocation path. Ownership and whether this is an unbounded leak remain open.

The second circuit records **four failed CMA attempts** for 4 MiB, with
`errorno=-16` (`EBUSY`). Two occur with only 959 pages (3.75 MiB) available
and two with 447 pages (1.75 MiB), all below the 1,024-page request.
Each enclosing `tegra_bo_create()` nevertheless
returned a valid object, flags `0x20` (`DONT_KMAP`, not `SPARSE`). This proves
successful allocation outside the failed CMA attempt, consistent with the
kernel DMA allocator's fallback. It does not establish sparse/GART allocation
or guarantee future fallback success. There were no new kernel log messages
or old large-request/cache-drop bursts in these four completed trials.

Xorg's log reports four new framebuffer allocations per circuit, alternating
1280×800 and 800×1280. Its active DRM framebuffer list has the same three IDs
before and after the second circuit. This narrows the investigation to display
buffer references, mappings and userspace caches rather than demonstrating a
growing DRM framebuffer-ID list.

## Limits and next fix

The installed DDX is based on a 2021 snapshot. The private source checkout is
`f78958d37c80b22de66f41167ec39339035f43d0` from 2023 and is not the installed
driver. Its display resize path creates a front buffer and destroys the old
one; its BO cache has age-based, activity-triggered cleanup. Those source paths
are useful leads, not proof of the exact installed cache policy or the cause
of the measured retention.

Next, trace the installed DDX's resize-buffer unref, mapping and cache ownership,
then compare a bounded rotation trial against the existing private DDX build.
Require evidence that old buffers are released or reuse reaches a stable bound
before selecting a fix. Increasing CMA would postpone pressure without resolving
this lifetime question. The historical 126.56 MiB request exceeds the whole
64 MiB CMA region, but its initiating client, dimensions and flags remain
unidentified; this checkpoint does not claim to fix it.

A separate screensaver query timed out on the live desktop bus. A read-only
GDB attachment did not establish a GPU-related cause, and no screensaver
activation trial completed. It is not counted as graphics validation here.
Physical touch and rotation were not reconfirmed by the user during this check.

## Evidence and repetition

[The checkpoint manifest](graphics-memory-checkpoint.json) records artifact
hashes, driver identity and measurements. [The evidence directory](evidence/graphics-memory-20261006)
contains original tablet reports/traces and host summaries. All completed
traces have zero overruns/dropped events, matching CMA counters and successful
probe cleanup. Reports include before/after kernel logs and per-CPU trace stats.
The first two trials used earlier revisions of the runner; their uploaded hashes
are recorded separately. The later reports embed the current runner's hash.

Upload the runner and the existing GTK fixture sequentially:

```sh
python3 scripts/ram_transfer.py upload scripts/tablet_graphics_memory_trial.py /tmp/tablet-graphics-memory-trial.py
python3 scripts/ram_transfer.py upload scripts/tablet_gtk_calendar_trial.py /tmp/tablet-gtk-calendar-trial.py
```

On the tablet root shell, use a fresh output path:

```sh
nohup python3 /tmp/tablet-graphics-memory-trial.py --cycles 6 --settle 45 \
  --output /tmp/graphics-memory-new > /tmp/graphics-memory-new.log 2>&1 < /dev/null &
```

For a rotation trial add `--rotation-check --cycles 1`. This temporarily stops
the rotation watcher, cycles the four orientations, restores the original
orientation and resumes the watcher. It does not save rotation settings.
A separate watchdog restores rotation and removes only the trial's uniquely
named probes/private trace instance after 360 seconds if the runner stalls.
ARM32 probes use AAPCS registers r1/r2 for size/flags rather than `$argN`.

Wait for the final report and process completion before downloading
`report.json` and `trace.txt`. A host console reader's time limit does not bound
the tablet job. Analyze the downloaded trace with:

```sh
python3 scripts/analyze_graphics_memory_trace.py /tmp/trace.txt --output /tmp/summary.json
```

Finally verified LightDM running, the original Xorg/XFCE PIDs present, the
rotation watcher resumed, 800×1280 left orientation restored, no remaining
trace instances/probes and 693.3 MiB normal RAM available. CMA bitmap headroom
was 4.12 MiB at the end of the final trace; later `CmaFree` was 3.23 MiB.
This leaves the working desktop available while retaining the evidence of
rotation pressure. No internal storage was written.
