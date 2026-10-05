/* SPDX-License-Identifier: MIT */
/* Invoke Tegra's existing forced-recovery restart handler. No storage writes. */
#include <errno.h>
#include <linux/reboot.h>
#include <stdio.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

int main(void)
{
    if (geteuid() != 0) {
        fputs("Root is required to restart into APX.\n", stderr);
        return 1;
    }
    sync();
    long result = syscall(SYS_reboot, LINUX_REBOOT_MAGIC1, LINUX_REBOOT_MAGIC2,
                          LINUX_REBOOT_CMD_RESTART2, "forced-recovery");
    if (result < 0)
        fprintf(stderr, "APX restart failed: %s\n", strerror(errno));
    return 1;
}
