# XFCE idle and calendar rendering checkpoint

Measured on the physical Indigo tablet on 2026-10-06, using the existing
external-SD root, kernel `7.0.1-nura-indigo-ram`, XFCE/X11 and the distribution
`opentegra` driver. No display-manager restart, renderer override, cache drop,
clock change or desktop configuration change was made by these tests.

## Observations

| Measurement | Five-minute idle observation | Calendar trial and recovery, two minutes |
| --- | --- | --- |
| Memory available | 716.5–726.8 MiB | 704.1–726.5 MiB |
| Average CPU busy, across both cores | 5.53% | 7.13% |
| Maximum logical zram swap used | 0.348 MiB | 0.348 MiB |
| Maximum measured temperature | 33.0°C | 32.75°C |
| Wi-Fi checks to the laptop over wlan0 | 31 successful, zero failed | 25 successful, zero failed |
| Xorg identity | PID 29643 throughout | Same PID throughout |
| XFCE session present | All 31 samples | All 25 samples |
| New kernel messages | None | None |

The foreground desktop was idle during the first phase, but diagnostic console
queries and the observer itself contributed some CPU and memory use. The second
phase includes application launch, framebuffer captures and recovery after the
window closes; its CPU figure is not a pure application cost or an FPS result.
These seven minutes are a bounded baseline, not an overnight stability test.
LAN pings do not validate internet service access.

The GTK3 calendar fixture ran as `julian` for 60.4 seconds and closed itself.
Its process RSS stayed at 33.23 MiB in the samples containing it. RSS includes
shared libraries and is not an exclusive memory cost. It displays the local
date and a month selector; no remote events are included.

GTK 3.24.52 drew the date heading, month, weekdays and selected day. A 620×680
Xorg client capture exactly matches the calendar region of the active DRM
framebuffer after accounting for the existing display rotation: **421,600 RGB
pixels compared, zero mismatches**. Both captures were also visually inspected
on the host. This verifies one real calendar frame through the display path,
not physical touchscreen interaction or every possible widget state.

Evidence and identities are in [xfce-stability-checkpoint.json](xfce-stability-checkpoint.json)
and [the evidence directory](evidence/xfce-20261006). The calendar fixture's own
report deliberately leaves `pixel_validation` false; the independent capture
comparison supplies that narrower validation.

## Graphics memory still needs attention

The existing kernel log contains bursts of 132,710,400-byte buffer allocation
failures alongside Xorg dropping page caches.
No new burst occurred in these observations. The diagnostic tools did not drop
caches. The current Xorg log reports a 24 MiB EXA pool, GART present and channel
IOMMU use reported as `NO`; `/proc/meminfo` reports a 64 MiB CMA region.

Source inspection explains the cache-drop retry: the DDX's
`src/tegradrm/tegra.c:drm_tegra_bo_new()` retries `ENOMEM` after writing
`1` to `/proc/sys/vm/drop_caches`. Its EXA allocator also has a normal-system-RAM
fallback for ordinary pixmaps. The active kernel's Grate allocation code in
`drivers/gpu/drm/grate/gem.c` chooses contiguous allocation by default for GART
unless a sparse allocation is requested. The initiating client/pixmap and its
allocation flags have not been traced, so this does not establish why those
particular requests are large or prove their final fallback succeeded.

`CmaFree` varied from 16.6 to 4.1 MiB during the idle phase and reached zero
in a calendar sample. It recovered to 6.25 MiB in the subsequent desktop
readout. Xorg RSS stayed at 35.75 MiB during the idle phase, and no allocation
failure or crash accompanied the sampled zero. These counts do not distinguish
movable ordinary pages, live graphics buffers and cached buffers, and do not
prove a leak or sufficient contiguous allocation headroom.

The follow-up [graphics allocation checkpoint](graphics-memory.md) traced
repeated application open/close and rotation. Calendar cycling retained only
1 MiB net and had approximately 20 MiB unreserved CMA space despite low
`CmaFree`. Rotation retained multiple 4 MiB buffers and reduced that space to
approximately 4 MiB; a repeated circuit produced failed CMA attempts with
successful enclosing GEM allocations. The historical large requests were not
reproduced. Rotation buffer ownership/release now needs investigation before
changing the reservation size.

## Repeat the bounded checks

The tablet already has Python and GTK3 introspection bindings. The observer
requires root on the verified external-SD system and fresh report paths under
`/tmp` or `/run`. The GUI fixture requires the desktop user and X11 access.
Use the console/transfer tools sequentially; finish a host serial operation
before starting another.

```sh
python3 scripts/ram_transfer.py upload scripts/monitor_xfce_stability.py /tmp/monitor-xfce-stability.py
python3 scripts/ram_transfer.py upload scripts/tablet_gtk_calendar_trial.py /tmp/tablet-gtk-calendar-trial.py
```

From the tablet root console, with a fresh output name and the current laptop
LAN address substituted for the example:

```sh
nohup python3 /tmp/monitor-xfce-stability.py --seconds 300 --interval 10 \
  --peer 192.168.0.147 --output /tmp/xfce-new-idle.json \
  > /tmp/xfce-new-idle.log 2>&1 < /dev/null &
```

Wait for the final report and process completion, then download it. The console
reader's `--seconds` bounds host observation, not the tablet job's lifetime.
For a calendar phase, start another bounded observer and launch the fixture:

```sh
su julian -c 'DISPLAY=:0 XAUTHORITY=/home/julian/.Xauthority GDK_BACKEND=x11 \
  python3 /tmp/tablet-gtk-calendar-trial.py --seconds 60 \
  --output /tmp/xfce-new-calendar-widget.json'
```

The fixture logs its X11 window ID. The existing `x-window-capture` probe reads
that client window; `graphics-stack-check --capture` reads the active DRM
framebuffer. The host comparison requires Pillow and returns nonzero if no
complete client match is found:

```sh
python3 scripts/compare_xfce_calendar_capture.py \
  docs/evidence/xfce-20261006/calendar-window.png \
  docs/evidence/xfce-20261006/calendar-scanout.png \
  --output /tmp/calendar-comparison.json
```

## Final state and next steps

Both observers and the calendar process finished. LightDM/XFCE stayed running;
the distribution driver, 800×1280 left rotation and three framebuffer objects
are unchanged. Only Xorg appears in DRM's active-client list. Final memory
available was 731.7 MiB, with the same 0.348 MiB logical swap use.

Fresh physical touch/rotation confirmation is pending. Prioritize the
graphics allocation investigation, then reproduce the verified XFCE setup in
a fresh SD image and test the selected applications on the tablet.
