# N-Trig silent-controller recovery, 2026-10-06

During installed-desktop validation, the user reported that taps stopped doing
anything. Xorg and XFCE were running, DPMS reported the monitor on, the
touchscreen remained enabled, and its transformation matched the left-rotated
display. A 25-second read-only evdev capture recorded zero events; the driver
continued SPI transfers but its packet and touch counters stayed at 9,684 and
642. No SPI error or invalid-packet counters increased. This locates the
observed silence below Xorg; it does not establish the original hardware or
firmware cause.

Reloading the N-Trig module power-cycled the controller. The user confirmed
touch worked again; the driver then recorded 144 new touch reports and resumed
control replies. The graphics driver was not changed to recover touch.

## Ported recovery

The pinned Lenovo source already contains a watchdog in
`sources/linux-stock/drivers/hid/ntrig_spi.c`: it checks communication, sends a
read-only firmware-version query during silence, and cycles sensor power after
three unanswered intervals. `ntrig_low_msg.c:build_low_bus_msg_short_cmd`
provides the exact command format. The initial modern transport port sent the
driver-alive command but had no recovery for continued silence.

The updated `port/ntrig-spi/ntrig_indigo.c` checks packet progress about once
per second, sends that read-only query when progress stops, and resets after
three missed intervals. Resets have a ten-second minimum spacing to avoid a
rapid power-cycle loop on persistent hardware failure. Before cycling power,
the driver releases active touch slots and pen state, clears the streaming
parser, and returns to the initial SPI transfer size. IRQ and poll work share
the same mutex. Existing input devices remain registered, preserving Xorg's
rotation mapping and device identity.

Root can invoke the same recovery path explicitly:

```sh
echo 1 > /sys/bus/spi/devices/spi0.0/recover
```

This writes no controller calibration or firmware. The read-only `stats`
attribute now includes `watchdog_misses` and `resets`. Reset messages distinguish
watchdog timeouts from administrator requests.

## Validation and bounds

The frozen kernel container built the module without warnings. The exact
hardware-tested artifact is `build/ntrig-watchdog/ntrig_indigo.ko`, SHA256
`73c4d277e1c7e5bc1831e5c21bcdeb0a1734ec37567647a14e81046a270aa127`.
The old module remains available separately for rollback.

On the tablet, the administrative recovery path completed, new controller
replies arrived, and Xorg retained PID 9006. A read-only observation checks
packet progress, error counters, resets, evdev events and Xorg start ticks;
its results are retained with the image evidence. This checks the actual
reset operation and normal operation after it. It does not reproduce the
original spontaneous silence or directly exercise automatic timeout recovery
against a physically unresponsive controller. Long-duration recurrence
monitoring remains necessary. Pen testing still requires batteries.

The [120-second observation](evidence/image-20261006/touch-watchdog-summary.json)
recorded 736 evdev events, 182 touch reports and 288 additional packets. There
were no additional resets, watchdog misses, SPI errors or invalid messages,
and Xorg's PID and start ticks stayed unchanged across all 24 samples.
Physical alignment confirmation for this module is still pending.

The new SD image contains this module and the previously verified graphics
fixes. Its dated input lock preserves the old image and module inputs rather
than changing an earlier image's dependencies. Fresh SD boot remains a
separate physical check.
