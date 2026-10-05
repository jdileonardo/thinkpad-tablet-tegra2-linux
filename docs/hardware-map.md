# Indigo hardware details to carry into the current kernel

These values come from the pinned historical ThinkPad port, unless marked
otherwise. They are a porting baseline; runtime support must be verified on
the attached unit.

| Component | Historical setting | Current validation |
| --- | --- | --- |
| USB device port | Tegra USB1 `0xc5000000`, UTMI PHY, `nvidia,tegra20-udc`, peripheral mode | USB ACM works on historical Linux and Nura 7.0.1, including the SD desktop |
| Display | LG LP101WX1, RGB, 1280×800, 6 bits per channel, 229×149 mm | Nura 7.0.1 XFCE desktop visually confirmed; Xrandr 1280×800, 60.33 Hz |
| Pixel timing | 71.5 MHz; horizontal front/sync/back 48/32/80; vertical front/sync/back 2/6/15 | Historical Linux panel driver, not U-Boot's different timings |
| Backlight | PWM2, 5,000,000 ns period; enable GPIO D4; backlight supply GPIO W0 | Driver loaded, readable display confirmed; brightness adjustment untested |
| Panel supply / enable | Supply GPIO C6; panel enable GPIO B2 | Working historical display path verified |
| eMMC | Controller `0xc8000600`, 8-bit, non-removable, power GPIO I6 | Linux enumerates MMC32G; boot-region backups verified; Android partitions require Tegra parser |
| External SD | Controller `0xc8000400`, 4-bit; power T3, detect I5 active low, write protect H1 active high | 64 GB SDXC card and ext4 OS root verified on Nura 7.0.1; current boot mmcblk0p1 |
| SDIO Wi-Fi | Controller `0xc8000000`, 4-bit; power K5, reset K6, PMC blink clock; BCM4329 firmware | Nura 7.0.1: scans, WPA2 association to Zone, DHCP, internet ping and HTTPS verified with Linux firmware 4.220.48 |
| Front / side keys | Q0 WWW, Q1 Home, Q2 Back, Q3 rotation lock, Q4 volume down, Q5 volume up | Linux validation pending |
| Power keys | C7 and I3, historical active high | Linux validation pending |
| Proximity | Historical GPIO C1 | Linux validation pending |
| Audio | WM8903 on I2C, Tegra I2S audio routing from historical Ventana port | WM8903/card detected; playback untested |
| Battery / EC | Stock Android EC_Battery at I2C2 address `0x58` | Stock readings available; no Linux charging integration verified |
| Touchscreen / pen | Stock N-Trig SPI0, CS0, mode 0, 3 MHz; power A5, output enable Q7, IRQ V6; SPID/SPIF pull-down, SPIE pull-up, pads enabled | Pad correction restored real finger position/down/up events; XFCE accepts both inputs after axis-resolution fix. User coordinate mapping and actual pen events pending |

The upstream Nura source has a modern Ventana device tree but no Indigo tree.
Its generic Ventana SD power pins, keys, and panel differ from the historical
ThinkPad settings. Do not use it unchanged as an Indigo device description.

Our dedicated `port/tegra20-lenovo-indigo.dts` overrides the board settings,
retaining modern CPU/core regulator constraints. The fixed `lg,lp101wx1`
descriptor is carried in `port/0001-panel-simple-add-indigo-panel.patch` and
has produced both readable console text and the physical XFCE desktop.

Keep CPU/core regulator constraints from the current Tegra source when
adapting the board. The old source has incomplete sensors and comments
describing unsupported accelerometer behavior; those comments are not proof
of working drivers.
