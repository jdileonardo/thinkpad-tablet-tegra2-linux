#!/usr/bin/env python3
"""Add a named Indigo DT and enable its USB device controller for RAM tests."""
from pathlib import Path

root = Path(__file__).resolve().parents[1]
dt = root / 'sources/linux-historical/arch/arm/boot/dts/tegra20-lenovo-indigo.dts'
dt.write_text('''// SPDX-License-Identifier: GPL-2.0
// Bootstrap from Dobrica Pavlinusic's ThinkPad-specific Ventana port.
#include "tegra20-ventana.dts"

/ {
    model = "Lenovo ThinkPad Tablet (Indigo) RAM test";
    compatible = "lenovo,indigo", "nvidia,ventana", "nvidia,tegra20";

    usb@c5000000 {
        compatible = "nvidia,tegra20-udc";
        dr_mode = "peripheral";
        status = "okay";
    };

    usb-phy@c5000000 {
        dr_mode = "peripheral";
        status = "okay";
    };
};
''')
print(f'Prepared {dt.name}')
