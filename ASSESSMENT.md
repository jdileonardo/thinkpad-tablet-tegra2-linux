# ThinkPad Tablet assessment — 2026-10-05

## Confirmed through USB ADB

- Lenovo ThinkPad Tablet, device codename `Indigo`, NVIDIA Tegra 2 / dual-core Cortex-A9, maximum reported CPU frequency 1 GHz.
- Android 4.0.3, API 15; build `ThinkPadTablet_A400_03_0070_0132_ROW`, dated August 23, 2012.
- Linux 2.6.39.4-g9b8008b-dirty.
- 32 GB class eMMC; `/data` reports about 27 GB usable, 17 GB free.
- 1 GB class RAM; kernel exposes about 715 MiB to Android, with substantial memory reserved for hardware.
- Display 1280 × 800; currently portrait.
- Existing `/system/bin/su` works: `su -c id` returns uid 0. No root exploit or installation was performed.
- Kernel config enables ARM EABI, VFPv3, loop devices, ext4; NEON and namespaces are disabled. CPU feature list also lacks NEON.
- LectureNotes 2.9.10, Notes Mobile, a PDF/ebook reader, browser, and media players are installed. App functionality has not been tested.
- Existing minimal BusyBox exposes only `fdisk`; `/system/xbin/chroot --help` returns `chroot: applet not found`. File presence alone does not establish a working Linux environment.
- Root access does not establish bootloader unlock status. Modern boot-lock properties are absent on this old Android version. Recovery type was not verified.

## Battery observations

Repeated snapshots over several minutes report the same state:

- External power classified as AC present; USB power classified as absent, despite a working USB data connection.
- Battery present, 0%, not charging, 3.351 V, 20.7 °C.
- Health reported as Good. This is a driver classification, not a measured capacity or proof that the battery is usable.
- Kernel repeatedly logs `EC_Bat_get_battery_property: No battery capacity` and `EC_Bat_get_battery_capacity: No battery capacity`.
- A gpio-charger probe also fails with error -16 during boot; this alone does not establish the charging failure's cause because the separate EC battery driver registers.
- No current, cycle count, or full-charge/design-capacity counters are exposed by the power-supply interface.

The user reports a very long time powered off and no visible physical damage. Deep discharge, battery degradation, power-source/cable limitations, and controller/charging faults remain possible. A battery failure is not yet proven.

Lenovo's original user guide says a computer USB connection may not charge the tablet with its display on. A useful next physical test is the original compatible wall charger/dock, with the tablet off, followed by another reading. Establish reliable power before any firmware writes.

## OS choices

1. **Keep rooted Android 4.0.3 for a dedicated task.** Most practical route for an offline PDF/notes device, photo display, or a simple custom native dashboard compiled for API 15 and ARMv7 without NEON. Installed readers and note applications make these plausible uses, pending functional testing. This does not provide current Android security or broad modern app compatibility.
2. **Historical CyanogenMod 10 / Android 4.1.2.** Device-specific source survives, but this is still a legacy Android version. ROM/recovery downloads, exact hardware variant, recovery procedure, and a restorable backup must be verified before installation. No flashable package was downloaded or validated in this investigation.
3. **Linux userspace alongside Android.** Root and loop/ext4 support are useful prerequisites. A suitable ARM userspace and working chroot tool would need to be supplied. Kernel 2.6.39 constrains modern userspace compatibility; an arbitrary current distro cannot be assumed to work. This route preserves Android's hardware drivers but does not replace its kernel or security model.
4. **Native Linux porting project.** Dobrica Pavlinusic demonstrated mainline-based Linux/Debian on this model in 2019, including display, audio, Wi-Fi, keys, and eMMC. Touchscreen, cameras, charging-controller integration, and some other hardware were incomplete. This is an engineering starting point rather than a verified current installer.

### Nura, formerly postmarketOS

The project announced its rename to **Nura** on September 27, 2026. The current release is v26.06 and a generic NVIDIA Tegra ARMv7 image exists. This is a promising base for porting, but it is not a universal installer for every Tegra tablet.

The current wiki was retrieved successfully through its public MediaWiki API after the regular page encountered an anti-bot challenge. The exact `lenovo-indigo` page still declares `packaged = no` and `booting = no`, with installation and hardware status fields unfilled. The generic Tegra page is currently categorized as `testing` and explicitly requires a compatible device and suitable U-Boot. Its current supported-device table does not include this ThinkPad.

A Nura effort for this tablet involves bringing its board-specific U-Boot/kernel/device tree into the generic Tegra platform and testing hardware. Subsequent porting experiments on this attached tablet confirmed developer mode and successfully booted the historical Linux kernel with a diagnostic initramfs entirely from RAM. USB shell and readable 1280×800 display output work; the Broadcom driver creates a Wi-Fi interface using stock firmware. A current Nura kernel/root filesystem, Wi-Fi association, touch, charging, and stable power still require work. See `PORTING.md` for the verified baseline and reproducible steps.

No verified modern Android/LineageOS installer for this exact Indigo device was found. Several search results labeled ThinkPad Tablet actually concern different Lenovo Tab models. Their images must not be treated as compatible.

For immediate usefulness, keep Android and choose a dedicated offline/local task. For substantial OS experimentation, investigate the native Linux work after securing backups and reliable power. CM10 offers a relatively small version increase.

## Sources and evidence

- CM10 author's source and build instructions: https://github.com/Koshu/thinkpad_tablet_device_tree_jb
- CM10 author's kernel: https://github.com/Koshu/thinkpad_tablet_jb_kernel
- Historical native Linux developer presentation, including hardware status: https://www.rot13.org/~dpavlin/presentations/dc2019-mainline_kernel_tegra20.pdf
- Native Linux source branch: https://github.com/dpavlin/linux/tree/thinkpad-tablet-phj00
- U-Boot source branch: https://github.com/dpavlin/u-boot/tree/phj00-thinkpad-tablet
- postmarketOS device page: https://wiki.postmarketos.org/wiki/Lenovo_ThinkPad_Tablet_(lenovo-indigo)
- Current Nura device page: https://wiki.nura.eco/wiki/Lenovo_ThinkPad_Tablet_(lenovo-indigo)
- Current generic Tegra page: https://wiki.nura.eco/wiki/Nvidia_Tegra_armv7_(nvidia-tegra-armv7)
- Official rename announcement: https://nura.eco/blog/2026/09/27/nura-rename/
- Current install/image list: https://nura.eco/install/
- Lenovo-authored original user guide mirror: https://images-na.ssl-images-amazon.com/images/I/B1ePq0AXcdS.pdf
- Lenovo hardware maintenance manual, downloaded successfully: https://download.lenovo.com/ibmdl/pub/pc/pccbbs/mobiles_pdf/tp_tablet_hmm_en_0a96158_04.pdf

Raw ADB output and the Lenovo hardware manual are in `diagnostics/`. Legacy `adb exec-out` failed; kernel config was recovered from shell output with its CRLF conversion reversed and successfully gzip-decompressed.
Current Nura wiki source and the rendered generic Tegra page are also saved in `diagnostics/`.

The initial ADB inspection was read-only. Subsequent authorized porting work saved verified firmware backups, entered APX recovery, and loaded custom U-Boot and a diagnostic Linux environment into RAM. No persistent firmware flash, repartition, wipe, app removal, or charging override has been performed. See `PORTING.md` for current experiment status.
