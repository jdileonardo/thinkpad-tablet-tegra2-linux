set -eu
stage="$OUT/rootfs"
mkdir -p "$stage/lib/modules/$KERNEL_RELEASE/kernel/drivers/input" \
    "$stage/lib/modules/$KERNEL_RELEASE/kernel/drivers/hid/usbhid" \
    "$stage/lib/modules/$KERNEL_RELEASE/kernel/drivers/reset" \
    "$stage/lib/modules/$KERNEL_RELEASE/extra"
cp /work/build/linux-nura/drivers/input/evdev.ko \
   "$stage/lib/modules/$KERNEL_RELEASE/kernel/drivers/input/"
cp /work/build/linux-nura/drivers/hid/hid-generic.ko \
   "$stage/lib/modules/$KERNEL_RELEASE/kernel/drivers/hid/"
cp /work/build/linux-nura/drivers/hid/usbhid/usbhid.ko \
   "$stage/lib/modules/$KERNEL_RELEASE/kernel/drivers/hid/usbhid/"
cp /work/build/linux-nura/drivers/reset/reset-gpio.ko \
   "$stage/lib/modules/$KERNEL_RELEASE/kernel/drivers/reset/"
cp "$NTRIG_MODULE" "$stage/lib/modules/$KERNEL_RELEASE/extra/ntrig_indigo.ko"
cp /work/build/linux-nura/modules.builtin /work/build/linux-nura/modules.builtin.modinfo \
   "$stage/lib/modules/$KERNEL_RELEASE/"
printf 'kernel/drivers/input/evdev.ko\nkernel/drivers/hid/hid-generic.ko\nkernel/drivers/hid/usbhid/usbhid.ko\nkernel/drivers/reset/reset-gpio.ko\nextra/ntrig_indigo.ko\n' \
    > "$stage/lib/modules/$KERNEL_RELEASE/modules.order"
python3 /work/scripts/image_kernel_modules.py --root "$stage" --project /work \
    --lock "$INPUT_LOCK" --release "$KERNEL_RELEASE"
depmod -b "$stage" "$KERNEL_RELEASE"
