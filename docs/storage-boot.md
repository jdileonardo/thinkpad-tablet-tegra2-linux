# Storage-loading U-Boot checkpoint

On 2026-10-06 the tablet successfully booted the validated XFCE SD system after
an APX download containing only U-Boot (498,484 bytes). U-Boot read the kernel,
bootstrap initramfs and Indigo device tree from SD and verified their SHA256
hashes before starting Linux. An independent read of the first 1 MiB of internal
eMMC matched the saved prefix. No internal storage was written.

## Builds and boot paths

The source remains pinned to the historical ThinkPad-compatible U-Boot commit
`385640388c84e405f817f8e747d4febaa0be0de5`. The builder is pinned to Docker ID
`sha256:bdeae42b66b5d1d1a70fe3f1505a17ba156eca8efdfa8364e9db3411e06beb2c`.
Generated configurations and output directories are separate from the released
RAM bootstrap; its artifacts and the existing image input lock remain intact.

| Profile | Purpose | U-Boot binary SHA256 |
| --- | --- | --- |
| `--nura-storage-test` | Storage loading with a known-good APX RAM fallback | `08aa3662c61377778c96c06446781f25bb80408600c4eef9eb6af82618d1f4ec` |
| `--nura-storage` | Storage loading with no preloaded Linux or RAM fallback | `6b1f990b85a18e12cd970e60c01d270488edc3fa4583b32202cf7c302375fdd2` |

Both builds use a transient environment and disable MMC writes, hardware
partitioning commands, ext4 writes and fastboot flashing. SHA256 verification
is enabled. The profiles use U-Boot `mmc0` for the internal device and `mmc1:1`
for the external SD partition. Linux currently enumerates those devices in the
opposite order.

The expected boot files are `/boot/vmlinuz-indigo`, `/boot/initramfs-indigo` and
`/boot/tegra20-lenovo-indigo.dtb`. Their sizes and hashes come from the released
RAM manifest and must match the frozen image input lock at build time. These
are deliberately pinned bring-up profiles; changing a boot file requires
regenerating this configuration. A later general-purpose installation boot
policy can support kernel updates without rebuilding U-Boot.

The test profile first copies the known-good preloaded files to spare RAM. If
storage loading fails, it restores them and boots with `indigo_boot=ram-fallback`
and a failure-stage marker. The storage-only profile enters non-flashing USB
fastboot if storage boot fails. Neither profile mounts or writes an internal
filesystem. Linux continues to use the original external-controller/UUID root
selection.

## Physical results

The first test downloaded the combined RAM test payload and returned:

```text
indigo_boot=sd-sha256 indigo_emmc=pass
```

This confirms storage reads and checks succeeded, rather than the RAM fallback.
The second test downloaded only the 498,484-byte U-Boot binary and produced the
same markers. XFCE started with the validated DDX and N-Trig module hashes;
the SD root was mounted, and both internal boot areas remained protected.
The early second-boot probe ran before Wi-Fi acquired an address; the later
[ready-state probe](evidence/storage-boot-20261006/uboot-only-ready.txt) confirmed
automatic Wi-Fi reconnection, three of three successful pings, XFCE running,
correct network time and both boot-area `force_ro` values still 1.

The first software reboot attempt entered Android and the user manually entered
APX. The next software APX restart succeeded. Both attempts first stopped XFCE,
synced storage and verified the SD root read-only. Physical recovery entry
remains the fallback; this checkpoint does not establish that every software
APX restart succeeds.

This proves U-Boot can start our Linux system from storage. It does not yet prove
cold boot from internal flash: U-Boot itself was downloaded through APX, using
the saved original board BCT. Generating the persistent BCT/boot image, defining
its bounded writes and recovery steps, and preparing the internal-root profile
remain before internal installation.

## Reproduce

```sh
bash scripts/build_uboot.sh --nura-storage-test
python3 scripts/make_ram_payload.py --profile nura-storage-test
bash scripts/build_uboot.sh --nura-storage
```

With the validated SD card in the tablet and the device freshly in APX, the
storage-only test downloads the small U-Boot binary into RAM:

```sh
bash scripts/tegrarcm.sh --usb-timeout=5000 \
  --bct=/work/backups/MP0GKR7-20261005T160450Z/active.bct \
  --bootloader=/work/build/uboot-nura-storage/u-boot-dtb-tegra.bin \
  --loadaddr=0x108000
```

The [test build plan](evidence/storage-boot-20261006/nura-storage-test-build.json),
[storage-only build plan](evidence/storage-boot-20261006/nura-storage-build.json),
[hybrid ready-state check](evidence/storage-boot-20261006/hybrid-boot-ready.txt),
[U-Boot-only APX transfer](evidence/storage-boot-20261006/uboot-only-apx-download.txt)
and [U-Boot-only startup check](evidence/storage-boot-20261006/uboot-only-startup.txt)
record source/configuration, artifact hashes and hardware evidence.
