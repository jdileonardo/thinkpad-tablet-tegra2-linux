# Release replaced XFCE scanout buffer references

The Xorg DDX now releases the previous scanout buffer reference when RandR
rebinds the existing screen pixmap. Before this fix, a complete rotation circuit
left four newly created 4 MiB buffers retained in the unpatched private driver.
After the fix, all newly created large buffers were freed in two completed
circuits, and CMA allocation headroom recovered to approximately 28–29 MiB.

This is a physical-tablet checkpoint on 2026-10-06, kernel
`7.0.1-nura-indigo-ram` with the external SD root. It follows the
[allocation investigation](graphics-memory.md). It does not resolve the old
132,710,400-byte allocation failures, certify arbitrary applications, or
constitute an overnight stability test.

## Cause and change

`tegra_exa_modify_pixmap_header()` took a reference to the newly selected front
buffer with `drm_tegra_bo_ref(scanout)` and overwrote `priv->bo`. Repeatedly
binding the same buffer added another reference; replacing it lost the previous
reference without an unref. The resize code destroyed its own old front-buffer
wrapper, but the pixmap reference kept that BO and its mapping alive.
The same attachment pattern existed for both rotated scanout paths.

Tracked patch
`port/opentegra/0003-release-replaced-scanout-pixmap-reference.patch` adds a shared
replacement helper. It retains the new BO before releasing the previous one,
and leaves the count unchanged when both pointers are equal. Before modifying
an existing scanout pixmap's dimensions/buffer, deferred operations are flushed
and its fences awaited using the DDX's existing helpers. Binding the ordinary
front buffer also clears the rotated-scanout flag.

No CMA reservation, memory clock or Mesa configuration was changed.
The updated DDX includes the previously validated DRI3 copy/export patches;
this selection does not globally select the experimental Mesa installation.

## Device verification

| Trial | Large BO creates | Newly created large BOs still live/cached at end | End CMA bitmap headroom | Net CMA reservation change | Failed CMA attempts |
| --- | --- | --- | --- | --- | --- |
| Distribution DDX, lifetime trace | 4 | 4 | 5.31 MiB | −0.06 MiB | 4 |
| Unpatched private DDX, three calendar cycles and 60 s settling | 6 | 4 | 11.79 MiB | +17.38 MiB | 1 |
| Fixed DDX, three calendar cycles and 60 s settling | 3 | 0 | 29.29 MiB | −0.25 MiB | 0 |
| Fixed DDX, repeat circuit, same calendar/settling | 2 | 0 | 28.18 MiB | +1.11 MiB | 0 |

All four traces have no failed GEM creates, no mapping errors, consistent CMA
counts, zero dropped events/overruns, unchanged before/after kernel logs and
complete owned-probe cleanup. The fixed trials ran for 126 and 125 seconds
on the same Xorg process, PID 12167. Kernel create counts include
session activity and potentially the initial automatic rotation; they are not
counts of rotation commands. The distribution session had already accumulated
pressure before its trace. Both private drivers were tested after a fresh Xorg
start, but these are bounded comparisons rather than an identical replay of all
desktop activity.

The fixed runs show that ordinary BO/mapping caches can temporarily consume
space: their minimum bitmap headroom was approximately 13 MiB. Those large
buffers were subsequently freed, unlike the unpatched retained references.
There remains small net retention in the second run; these measurements do not
prove that every other cache has an ideal policy or rule out all memory leaks.

After the repeated circuit, a GTK3 calendar ran for 40.4 seconds. A complete
620×680 X11 client capture matched its region in the rotated active DRM scanout:
**421,600 RGB pixels compared, zero mismatches**. The client capture was also
visually inspected. This verifies the displayed frame under the fixed driver,
not physical input or all intermediate frames.

### Instrumentation interpretation

The lifetime trace follows GEM creation/free, mapping creation/close and handle
reference release. `drm_gem_object_handle_put_unlocked()` is also called by DRM
framebuffer cleanup; it is **not** proof of userspace GEM_CLOSE. The early
progress update interpreting those puts as Xorg handle closes was too strong.
The fixed traces therefore also probe `drm_gem_object_release_handle()` to
identify actual file-handle releases. `tegra_bo` embeds `drm_gem_object` first,
so these object addresses match the BO pointer ledger.

A read-only GDB cache inspection attempt detached without collecting cache
state because the private module lacks the required C type debug information.
Its tiny DWARF sections cover assembly, not the DDX structures. No conclusion
about cache ownership is based on that unsuccessful inspection.

## Installed selection and rollback

The verified module is installed at
`/opt/indigo-xorg/xfce/lib/xorg/modules/drivers/opentegra_drv.so`, SHA256
`7f5350d475af38789b38bea7a816ea75547a5e1728e40c5a6face84909770735`.
`/etc/lightdm/lightdm.conf.d/95-indigo-xorg.conf` selects its module directory
and a small EXA configuration. The temporary trial was restored before making
this persistent selection. LightDM was restarted; its new Xorg log confirms
loading the fixed module from the XFCE prefix. The original distribution
module remains unchanged, SHA256
`5864c997b380945501b998b6829c071bb804d4df2f479f902f51a991e9682d97`.
The previous private module is retained separately on the SD card.

`scripts/install_indigo_xorg.py` checks the external SD controller and artifact
hash and refuses an active trial or an unrelated existing selection. To select
the fixed artifact after transferring it to `/tmp`:

```sh
python3 /tmp/install-indigo-xorg.py --module /tmp/opentegra-rotation-fixed.so \
  --sha256 7f5350d475af38789b38bea7a816ea75547a5e1728e40c5a6face84909770735
```

To return to the distribution driver from the root console:

```sh
python3 /tmp/install-indigo-xorg.py --restore-stock
```

Both commands restart LightDM. They retain the user's login/rotation settings
and private artifacts. The installer rolls back its selection if the service
restart reports failure; a successful restart is still followed by device
checks. The final readout confirms the selected module, LightDM running,
800×1280 left orientation, and no remaining diagnostic trace instances/probes.
Touch/pen still enumerate and three Wi-Fi pings to the laptop pass after the
restart. Fresh user confirmation of physical touch remains pending.

## Release follow-ups

Source identities, hashes and measurements are in
[graphics-rotation-fix-checkpoint.json](graphics-rotation-fix-checkpoint.json)
and [the evidence directory](evidence/graphics-lifetime-20261006).
The fix is also a commit in the local upstream DDX branch; see
[source branches and image readiness](source-branches.md).

Next, reproduce the selected components in the SD image, boot that image
repeatedly, and measure sustained calendar/controller use. The earlier large
allocation requests still need attribution if reproduced. RGB565/Qt and KWin
capability defects remain deferred with Plasma; the hardware GPU is not being
claimed as a complete general-purpose rendering implementation. Internal
installation and autonomous boot remain separate device-specific work.
