// SPDX-License-Identifier: GPL-2.0-only
/* Read-only evdev capture for physical touch/pen validation. */
#include <linux/input.h>
#include <fcntl.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    struct pollfd fds[16];
    unsigned long counts[16] = {0};
    struct timespec start, now;
    int seconds, n;
    if (argc < 3 || argc > 18) {
        fprintf(stderr, "usage: %s SECONDS /dev/input/event...\n", argv[0]);
        return 2;
    }
    seconds = atoi(argv[1]);
    if (seconds < 1 || seconds > 300) return 2;
    setvbuf(stdout, NULL, _IOLBF, 0);
    n = argc - 2;
    for (int i = 0; i < n; i++) {
        char name[128] = {0};
        fds[i].fd = open(argv[i + 2], O_RDONLY | O_NONBLOCK);
        if (fds[i].fd < 0) { perror(argv[i + 2]); return 1; }
        fds[i].events = POLLIN;
        ioctl(fds[i].fd, EVIOCGNAME(sizeof(name)), name);
        printf("device %s: %s\n", argv[i + 2], name);
    }
    clock_gettime(CLOCK_MONOTONIC, &start);
    do {
        if (poll(fds, n, 250) < 0) { perror("poll"); return 1; }
        for (int i = 0; i < n; i++) {
            struct input_event events[64];
            ssize_t bytes;
            if (fds[i].revents & (POLLERR | POLLHUP | POLLNVAL)) return 1;
            while ((bytes = read(fds[i].fd, events, sizeof(events))) > 0) {
                for (unsigned int j = 0; j < bytes / sizeof(events[0]); j++) {
                    struct input_event *e = &events[j];
                    printf("%s %ld.%06ld type=%u code=%u value=%d\n", argv[i+2],
                        (long)e->time.tv_sec, (long)e->time.tv_usec,
                        e->type, e->code, e->value);
                    counts[i]++;
                }
            }
        }
        clock_gettime(CLOCK_MONOTONIC, &now);
    } while (now.tv_sec - start.tv_sec < seconds);
    for (int i = 0; i < n; i++) {
        printf("total %s: %lu events\n", argv[i + 2], counts[i]);
        close(fds[i].fd);
    }
    return 0;
}
