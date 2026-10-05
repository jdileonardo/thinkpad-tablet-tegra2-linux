# Indigo hardware details to carry into the current kernel

These values come from the pinned historical ThinkPad port, unless marked
otherwise. They are a porting baseline; runtime support must be verified on
the attached unit.

| Component | Historical setting | Current validation |
| --- | --- | --- |
| USB device port | Tegra USB1 `0xc5000000`, UTMI PHY, `nvidia,tegra20-udc`, peripheral mode | Diagnostic USB ACM enumerated on this tablet |
| Display | LG LP101WX1, RGB, 1280×800, 6 bits per channel, 229×149 mm | Linux DRM framebuffer and readable screen text verified |
| Pixel timing | 71.5 MHz; horizontal front/sync/back 48/32/80; vertical front/sync/back 2/6/15 | Historical Linux panel driver, not U-Boot's different timings |
| Backlight | PWM2, 5,000,000 ns period; enable GPIO D4; backlight supply GPIO W0 | Driver loaded, readable display confirmed; brightness adjustment untested |
| Panel supply / enable | Supply GPIO C6; panel enable GPIO B2 | Working historical display path verified |
| eMMC | Controller `0xc8000600`, 8-bit, non-removable, power GPIO I6 | Linux enumerates MMC32G; boot-region backups verified; Android partitions require Tegra parser |
| External SD | Controller `0xc8000400`, 4-bit; power T3, detect I5 active low, write protect H1 active high | Linux validation pending |
| SDIO Wi-Fi | Controller `0xc8000000`, historical 8-bit setting; BCM4329 firmware required | SDIO ID 02d0:4329; stock firmware loads, wlan0 can be brought up; no association tested |
| Front / side keys | Q0 WWW, Q1 Home, Q2 Back, Q3 rotation lock, Q4 volume down, Q5 volume up | Linux validation pending |
| Power keys | C7 and I3, historical active high | Linux validation pending |
| Proximity | Historical GPIO C1 | Linux validation pending |
| Audio | WM8903 on I2C, Tegra I2S audio routing from historical Ventana port | WM8903/card detected; playback untested |
| Battery / EC | Stock Android EC_Battery at I2C2 address `0x58` | Stock readings available; no Linux charging integration verified |
| Touchscreen / pen | Historical native port did not report working touch | Requires separate driver and wiring investigation |

The current Nura source has a modern Ventana device tree but no Indigo tree.
Its generic Ventana SD power pins, keys, and panel differ from the historical
ThinkPad settings. Do not use it unchanged as an Indigo device description.

Historical Linux adds an `lg,lp101wx1` panel description in `panel-simple.c`.
The current kernel offers a generic `panel-dpi` path that may express the
same fixed timing without carrying that historical driver patch. Its binding
and RGB format must be checked before choosing this approach.

Keep CPU/core regulator constraints from the current Tegra source when
adapting the board. The old source has incomplete sensors and comments
describing unsupported accelerometer behavior; those comments are not proof
of working drivers.
