/* Verify X drawing/readback for an ordinary and a large CPU-fallback pixmap. */
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

static int errors;
static int xerror(Display *d, XErrorEvent *e)
{
    char message[256];
    XGetErrorText(d, e->error_code, message, sizeof(message));
    fprintf(stderr, "X error: %s request=%u minor=%u\n", message, e->request_code, e->minor_code);
    errors++;
    return 0;
}

int main(void)
{
    Display *d = XOpenDisplay(NULL);
    if (!d) return 1;
    XSetErrorHandler(xerror);
    int screen = DefaultScreen(d);
    unsigned sizes[] = {640, 5760};
    printf("probe_pid=%ld\n", (long)getpid());
    for (unsigned trial = 0; trial < 2; trial++) {
        unsigned size = sizes[trial];
        Pixmap p = XCreatePixmap(d, RootWindow(d, screen), size, size, DefaultDepth(d, screen));
        GC gc = XCreateGC(d, p, 0, NULL);
        unsigned long colors[] = {0x12ab34, 0xe54c27};
        int points[][2] = {{8, 8}, {(int)size - 40, (int)size - 40}};
        for (unsigned i = 0; i < 2; i++) {
            XSetForeground(d, gc, colors[i]);
            XFillRectangle(d, p, gc, points[i][0], points[i][1], 32, 32);
        }
        XSync(d, False);
        if (errors) return 2;
        unsigned checked = 0;
        for (unsigned i = 0; i < 2; i++) {
            XImage *image = XGetImage(d, p, points[i][0], points[i][1], 32, 32, AllPlanes, ZPixmap);
            if (!image || errors) return 3;
            for (int y = 0; y < 32; y++)
                for (int x = 0; x < 32; x++) {
                    if ((XGetPixel(image, x, y) & 0xffffff) != colors[i]) return 4;
                    checked++;
                }
            XDestroyImage(image);
        }
        printf("pixmap=0x%lx size=%ux%u depth=%u pixels_checked=%u PASS\n",
               p, size, size, DefaultDepth(d, screen), checked);
        fflush(stdout);
        XFreeGC(d, gc);
        XFreePixmap(d, p);
        XSync(d, False);
    }
    XCloseDisplay(d);
    return errors ? 5 : 0;
}
