# Build, copy, flash and upstream the Indigo port

This guide follows the internal installation in commit `e5efcbb`, with the
subsequent verified [CPU scaling integration](power-bringup.md).
The target is the original Tegra20 Lenovo ThinkPad Tablet (Indigo). Normal ROM
restarts into internal XFCE passed. Physical cold power-on with the SD removed
is still pending in the [installation record](internal-install.md).

## What is repeatable today

| Operation | Status |
| --- | --- |
| Assemble and check an SD image using frozen inputs | Scripted; current default pins 68 inputs and four assembler/toolchain containers, including verified CPU scaling |
| Write the SD image and check its full readback | Tested with our USB card reader; accepts an image manifest and fresh disk identity |
| Build the internal image and persistent boot image | Scripted for this checkpoint; still depends on dated paths and this board's saved BCT |
| Transfer files to the diagnostic Linux system | Scripted USB upload/download with end-to-end SHA256; bulk image transfer used Wi-Fi |
| First installation on this tablet | Tested, guarded scripts and complete write/readback evidence |
| Reflash the already installed tablet, or install another unit | Requires a reusable installer; the archived first-install scripts deliberately refuse these states |
| Build everything on a clean machine from source | Not yet verified end to end; Git alone does not contain the ignored source trees and binary inputs |

The earlier 66-input lock remains archived as
`port/image-inputs-touch-watchdog.lock.json`. The current default and
`port/image-inputs-cpufreq.lock.json` include the verified cpufreq module and
its integration manifest. Filesystem timestamps, UUIDs and password salts can
change image hashes, so repeatable assembly does not mean byte-identical disks.

## Preserve the build inputs

Keep these alongside the Git repository, outside public source submissions:

- `build/image-inputs-touch-watchdog/frozen-inputs.tar`, `containers.tar.gz`
  and `export-manifest.json`: the locked binary inputs and Docker images.
- The validated SD and internal image directories and their manifests.
- `build/internal-boot-20261006/`: the persistent boot image and manifest.
- The original board BCT, boot-area backups and known-good APX/SD payload.
- A separate record of local login and NetworkManager configuration. The
  portable frozen-input export deliberately excludes these private inputs.

Verify archive hashes against `export-manifest.json` before restoring them.
Extract `frozen-inputs.tar` into a fresh project checkout with numeric ownership
preserved, then load the container archive:

```sh
gzip -dc /path/to/containers.tar.gz | docker load
```

The four-container export covers image assembly and the current kernel/Mesa/DDX
builders. It does not include the historical U-Boot builder, every ignored
source checkout, the BusyBox binary, the original BCT or the live pmbootstrap
firmware paths needed to regenerate the internal bootstrap. Preserve those
separately until a complete source/bootstrap recipe replaces them. Exact source
URLs and revisions are in `sources.lock.json`.

## Assemble and verify an SD image

Run from the project root with Docker access and Python 3.11 or newer. Use a
fresh output directory; builders refuse to replace existing images. Allow
several GiB of free space for assembly, filesystem checks and image copies.

```sh
python3 scripts/create_nura_sd_image.py \
  --lock port/image-inputs.lock.json \
  --output build/nura-sd-next \
  --password-file build/image-inputs/login-password

python3 scripts/verify_nura_sd_image.py \
  --manifest build/nura-sd-next/image-manifest.json
```

Create the private password file first. Add `--network-profile` with a keyfile
under `build/` only for a private image. The currently installed image includes
our Wi-Fi configuration and requested login settings; it is not a public
release image. See [frozen inputs and rebuild](xfce-image.md#frozen-inputs-and-rebuild).

The assembler uses verified binary inputs. Rebuilding kernel, N-Trig, Mesa or
DDX creates candidate artifacts; review and freeze a new input lock before
using them in a release. Existing builders include `build_nura_kernel.sh`,
`build_ntrig_module.sh`, `build_mesa_grate.sh` and `build_opentegra.sh`.
Confirmed additions must enter their build/packaging recipe, startup
configuration, verification and current input lock together. See the
[promotion workflow](development-workflow.md#promoting-verified-device-changes).
To reproduce the historical image, explicitly select the archived 66-input lock.

## Copy an image onto an SD card

Freshly identify the removable whole USB disk. Substitute the actual values
below; do not reuse a historical `/dev/sdX` assignment. Unmount its partitions.
This command erases the selected card.

```sh
lsblk -b -o NAME,PATH,SIZE,MODEL,SERIAL,RM,TYPE,MOUNTPOINTS,TRAN

python3 scripts/write_nura_sd.py \
  --manifest build/nura-sd-next/image-manifest.json \
  --device /dev/ACTUAL_WHOLE_DISK \
  --expected-serial ACTUAL_READER_SERIAL \
  --expected-size ACTUAL_CARD_BYTES
```

The current writer also requires our `USB3.0 CRW -SD` reader model and an existing
first-partition node. It checks identity and source hash, writes, verifies every
written byte, expands ext4 and records evidence. A different reader or blank
unpartitioned card needs an explicit writer adjustment.

For recovery, insert the working SD and enter APX physically, then use the
preserved payload and BCT:

```sh
bash scripts/tegrarcm.sh --usb-timeout=5000 \
  --bct=/work/backups/MP0GKR7-20261005T160450Z/active.bct \
  --bootloader=/work/build/nura-sd-test/thinkpad-ram-payload.bin \
  --loadaddr=0x108000
```

This tested RAM payload selects the SD controller/UUID and ignores extlinux.
The SD's automatic extlinux entry was saved as
`/boot/extlinux/extlinux.conf.sd-recovery`; restoring the original filename
re-enables SD-first normal boot. Serialize diagnostic console and transfer calls.

## Generate the checkpoint's internal images

These are host-only commands using the existing preserved checkpoint inputs;
they do not write the tablet:

```sh
python3 scripts/make_ramdisk.py --profile nura-internal \
  --root-uuid a1b59fdc-49f7-46bb-b099-4c6012334c07
python3 scripts/create_internal_root_image.py \
  --source-manifest build/nura-sd-next/image-manifest.json \
  --output build/nura-internal-next

bash scripts/build_uboot.sh --nura-extlinux
python3 scripts/build_internal_boot_image.py --output build/internal-boot-next
```

The internal builder requires the selected SD manifest, verifies its image,
input lock and filesystem hashes, and checks that its verified modules and
startup entries survive adaptation. It takes the UUID from
`build/internal-root.uuid` and bootstrap from `build/nura-internal-test`.
A new UUID or kernel/bootstrap checkpoint still requires updating those
inputs and deployment checks together. It never silently selects the old
dated SD image.

The bootstrap generator requires the preserved BusyBox, firmware, regulatory
database and APX helper inputs. The boot-image builder requires the pinned
`sources/cbootimage` checkout with built `cbootimage`/`bct_dump` executables,
a host C compiler, OpenSSL's `mac` command, the historical U-Boot container
`sha256:bdeae42b66b5d1d1a70fe3f1505a17ba156eca8efdfa8364e9db3411e06beb2c`,
and this tablet's original BCT. These prerequisites are not all in the four
container/input export. Never substitute a BCT from an unrelated unit.

## Transfer and internal flash

`scripts/ram_transfer.py upload LOCAL /tmp/REMOTE` copies small files with a
verified checksum. `scripts/ram_console.py --command 'COMMAND'` executes commands
on the diagnostic USB shell. A returned running session must finish before
another console or transfer call.

For bulk transfer, gzip the selected image, transfer it over the working network
to the recovery SD filesystem, and compare both compressed and decompressed
SHA256 values with the selected manifests. Our installed system has no assumed
SSH service. The previous transfer's temporary IP addresses/server are not a
permanent deployment interface.

The executed first installation used:

1. `port/internal/boot0-install.sh --check`, then `--apply`, against the prepared
   2 MiB boot0 image. It verified full readback, restored write protection and
   checked untouched boot1/main-prefix contents.
2. A normal ROM restart into the SD root without an APX download.
3. `port/internal/user-area-install.sh --apply` from the SD recovery root, with
   the matching whole image and expanded MBR. It verified every written byte,
   expanded the partition/filesystem and checked boot-area hashes again.
4. Read-only inspection of the installed root, disabling the SD extlinux entry,
   a normal restart and internal controller/UUID/runtime checks.

Both scripts pin this unit's CID/capacity, the original Android prefix and exact
artifact hashes. The boot0 script also requires the original boot0 hash.
Those original states are now gone. Running these archived scripts again will
refuse; removing their checks is not a reflash procedure. The expanded MBR was
generated for this exact image/capacity and is another input to generalize.
The [installation plan and logs](internal-install.md) preserve the executed
recipe and its checks, rather than promising a general installer.

For routine development, keep the installed U-Boot and update versioned kernel,
initramfs/DTB files through extlinux, or deploy userspace components in place.
Keep known-good files and the tested SD/APX recovery setup. A whole-root reflash
needs an offline recovery boot and a manifest-based installer that accepts the
current Linux layout as its explicitly verified starting state.

## Preparing upstream submissions

The [source branches](source-branches.md) contain local kernel, DDX and candidate
Mesa commits and exported patch series. No public push or submission has occurred.
The proposed destinations are:

| Work | Proposed destination and preparation |
| --- | --- |
| Device packaging, firmware references, desktop helpers and supported install procedure | Nura device packages; replace local paths/account configuration and private firmware extraction with documented packaging |
| Indigo DTS/panel and N-Trig SPI support | Kernel maintainers, initially coordinated with libre-tegra; add bindings/in-tree integration and subsystem review |
| DDX scanout reference and large-pixmap fixes | `libre-tegra/xf86-video-opentegra`; prepare focused patches with reproducer and hardware evidence |
| Tegra DMA-BUF and Mesa changes | The corresponding libre-tegra trees; separate production fixes from diagnostic toggles and unsupported-format experiments |
| Persistent boot setup | Board-specific bootloader/install packaging; the current historical U-Boot changes have not been exported as an upstream-ready series |

The existing kernel branch contains panel, DMA-BUF and DTS changes. The N-Trig
driver is still an out-of-tree module under `port/ntrig-spi`; it is not included
in that exported kernel branch. U-Boot and device packaging also need separate
submission work. Mainline-kernel readiness is distinct from working on the
libre-tegra kernel base.

Start with the focused, hardware-tested DDX fixes and a documented device port.
Rebase submissions onto each maintainer's requested current tree, write
self-contained commit descriptions with evidence and required sign-offs, and
run the relevant build/style/binding checks. Preserve the working pinned build
while preparing review worktrees. Nura's
[contribution guide](https://nura.eco/contribute/) describes device porting and
upstream contributions; the kernel's
[submission guide](https://docs.kernel.org/process/submitting-patches.html)
describes patch preparation and subsystem workflows.
