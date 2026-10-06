/* Save the actual Xorg window pixels independently of compositor readback. */
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <stdio.h>
#include <stdlib.h>

static unsigned char channel(unsigned long pixel, unsigned long mask)
{
    if (!mask) return 0;
    while (!(mask & 1)) { pixel >>= 1; mask >>= 1; }
    return ((pixel & mask) * 255 + mask / 2) / mask;
}
int main(int argc, char **argv)
{
    if (argc != 3) { fprintf(stderr, "Usage: %s WINDOW_ID OUTPUT.ppm\n", argv[0]); return 1; }
    Display *d = XOpenDisplay(NULL);
    if (!d) return 1;
    char *end;
    Window window = strtoul(argv[1], &end, 0);
    if (*end) return 1;
    XWindowAttributes a;
    if (!XGetWindowAttributes(d, window, &a)) return 1;
    XImage *image = XGetImage(d, window, 0, 0, a.width, a.height, AllPlanes, ZPixmap);
    if (!image) return 1;
    FILE *f = fopen(argv[2], "wb");
    if (!f) return 1;
    fprintf(f, "P6\n%d %d\n255\n", a.width, a.height);
    for (int y = 0; y < a.height; ++y)
        for (int x = 0; x < a.width; ++x) {
            unsigned long pixel = XGetPixel(image, x, y);
            unsigned char rgb[3] = {channel(pixel, image->red_mask),
                                   channel(pixel, image->green_mask),
                                   channel(pixel, image->blue_mask)};
            if (fwrite(rgb, 3, 1, f) != 1) return 1;
        }
    if (fclose(f)) return 1;
    printf("CAPTURE PASS window=%lu size=%dx%d file=%s\n", window, a.width, a.height, argv[2]);
    XDestroyImage(image); XCloseDisplay(d);
    return 0;
}
