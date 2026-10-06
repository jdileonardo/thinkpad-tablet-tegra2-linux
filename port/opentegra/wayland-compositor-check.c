/* CPU-produced Wayland surfaces, composed by Weston, sampled through Xorg.
 * The test process never creates a GL context or renders the expected output. */
#define _GNU_SOURCE
#include <wayland-client.h>
#include "xdg-shell-client-protocol.h"
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static struct wl_compositor *compositor;
static struct wl_subcompositor *subcompositor;
static struct wl_shm *shm;
static struct xdg_wm_base *wm;
static int configured, frame_finished, width = 640, height = 480;
static void fatal(const char *message) { fprintf(stderr, "%s\n", message); exit(1); }
static void ping(void *data, struct xdg_wm_base *base, uint32_t serial)
{ (void)data; xdg_wm_base_pong(base, serial); }
static const struct xdg_wm_base_listener wm_listener = { .ping = ping };
static void global(void *data, struct wl_registry *registry, uint32_t name,
                   const char *interface, uint32_t version)
{
    (void)data;
    if (!strcmp(interface, "wl_compositor"))
        compositor = wl_registry_bind(registry, name, &wl_compositor_interface, version < 4 ? version : 4);
    else if (!strcmp(interface, "wl_subcompositor"))
        subcompositor = wl_registry_bind(registry, name, &wl_subcompositor_interface, 1);
    else if (!strcmp(interface, "wl_shm"))
        shm = wl_registry_bind(registry, name, &wl_shm_interface, 1);
    else if (!strcmp(interface, "xdg_wm_base")) {
        wm = wl_registry_bind(registry, name, &xdg_wm_base_interface, 1);
        xdg_wm_base_add_listener(wm, &wm_listener, NULL);
    }
}
static void removed(void *data, struct wl_registry *registry, uint32_t name)
{ (void)data; (void)registry; (void)name; }
static const struct wl_registry_listener registry_listener = { .global = global, .global_remove = removed };
static void configure(void *data, struct xdg_surface *surface, uint32_t serial)
{ (void)data; xdg_surface_ack_configure(surface, serial); configured = 1; }
static const struct xdg_surface_listener surface_listener = { .configure = configure };
static void top_configure(void *data, struct xdg_toplevel *top, int32_t w,
                          int32_t h, struct wl_array *states)
{ (void)data; (void)top; (void)states; if (w > 0) width = w; if (h > 0) height = h; }
static void top_close(void *data, struct xdg_toplevel *top)
{ (void)data; (void)top; fatal("toplevel closed"); }
static const struct xdg_toplevel_listener top_listener = { .configure = top_configure, .close = top_close };
static void frame_done(void *data, struct wl_callback *callback, uint32_t time)
{ (void)data; (void)time; frame_finished = 1; wl_callback_destroy(callback); }
static const struct wl_callback_listener frame_listener = { .done = frame_done };
static struct wl_buffer *buffer(int w, int h, uint32_t color)
{
    size_t size = (size_t)w * h * 4;
    int fd = memfd_create("indigo-compositor-fixture", MFD_CLOEXEC);
    if (fd < 0 || ftruncate(fd, size)) fatal("memfd failed");
    uint32_t *pixels = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (pixels == MAP_FAILED) fatal("shm mmap failed");
    for (size_t i = 0; i < size / 4; ++i) pixels[i] = color;
    struct wl_shm_pool *pool = wl_shm_create_pool(shm, fd, size);
    struct wl_buffer *b = wl_shm_pool_create_buffer(pool, 0, w, h, w * 4, WL_SHM_FORMAT_ARGB8888);
    wl_shm_pool_destroy(pool); munmap(pixels, size); close(fd);
    return b;
}
static unsigned channel(unsigned long pixel, unsigned long mask)
{
    if (!mask) return 0;
    while (!(mask & 1)) { pixel >>= 1; mask >>= 1; }
    return ((pixel & mask) * 255 + mask / 2) / mask;
}
int main(int argc, char **argv)
{
    if (argc != 2) fatal("Usage: wayland-compositor-check WESTON_X_WINDOW_ID");
    setvbuf(stdout, NULL, _IONBF, 0);
    char *end;
    Window window = strtoul(argv[1], &end, 0);
    if (*end) fatal("invalid X window ID");
    Display *x = XOpenDisplay(NULL);
    struct wl_display *d = wl_display_connect(NULL);
    if (!x || !d) fatal("X11/Wayland connect failed");
    struct wl_registry *registry = wl_display_get_registry(d);
    wl_registry_add_listener(registry, &registry_listener, NULL);
    if (wl_display_roundtrip(d) < 0 || !compositor || !subcompositor || !shm || !wm)
        fatal("missing Wayland globals");
    struct wl_surface *parent = wl_compositor_create_surface(compositor);
    struct xdg_surface *surface = xdg_wm_base_get_xdg_surface(wm, parent);
    xdg_surface_add_listener(surface, &surface_listener, NULL);
    struct xdg_toplevel *top = xdg_surface_get_toplevel(surface);
    xdg_toplevel_add_listener(top, &top_listener, NULL);
    xdg_toplevel_set_title(top, "Indigo compositor pixel test");
    xdg_toplevel_set_fullscreen(top, NULL);
    wl_surface_commit(parent);
    while (!configured) if (wl_display_dispatch(d) < 0) fatal("configure failed");
    XWindowAttributes a;
    if (!XGetWindowAttributes(x, window, &a) || a.width != width || a.height != height || width < 256 || height < 192)
        fatal("fullscreen/output size mismatch");
    struct wl_surface *child = wl_compositor_create_surface(compositor);
    struct wl_subsurface *sub = wl_subcompositor_get_subsurface(subcompositor, child, parent);
    wl_subsurface_set_position(sub, 32, 32);
    const uint32_t base[] = {0xff0000ff, 0xff00ff00, 0xffff0000};
    const uint32_t over[] = {0x80800000, 0x80000080, 0x80808080};
    const uint32_t blended[] = {0x80007f, 0x007f80, 0xff8080};
    struct wl_buffer *buffers[24];
    unsigned samples = 0;
    for (unsigned frame = 0; frame < 12; ++frame) {
        unsigned color = frame % 3;
        buffers[frame * 2] = buffer(width, height, base[color]);
        buffers[frame * 2 + 1] = buffer(192, 128, over[color]);
        wl_surface_attach(child, buffers[frame * 2 + 1], 0, 0);
        wl_surface_damage(child, 0, 0, 192, 128); wl_surface_commit(child);
        wl_surface_attach(parent, buffers[frame * 2], 0, 0);
        frame_finished = 0;
        wl_callback_add_listener(wl_surface_frame(parent), &frame_listener, NULL);
        wl_surface_damage(parent, 0, 0, width, height); wl_surface_commit(parent);
        while (!frame_finished)
            if (wl_display_dispatch(d) < 0) fatal("frame callback failed");
        /* The first repaint includes shader compilation and the shell's fade.
         * Later frames have no shell transition; they retain the shorter wait. */
        usleep(frame == 0 ? 3000000 : 500000);
        XSync(x, False);
        XImage *image = XGetImage(x, window, 0, 0, width, height, AllPlanes, ZPixmap);
        if (!image) fatal("XGetImage failed");
        const int points[][2] = {{8,8}, {width-8,height-8}, {40,40}, {200,140}};
        for (unsigned i = 0; i < 4; ++i) {
            unsigned long pixel = XGetPixel(image, points[i][0], points[i][1]);
            unsigned actual[3] = {channel(pixel, image->red_mask), channel(pixel, image->green_mask), channel(pixel, image->blue_mask)};
            uint32_t expected = i < 2 ? base[color] : blended[color];
            int pass = 1;
            for (unsigned j = 0; j < 3; ++j)
                if (abs((int)actual[j] - (int)((expected >> (16 - j * 8)) & 255)) > 2) pass = 0;
            printf("sample=%u frame=%u x=%d y=%d rgb=%u,%u,%u expected=%06x %s\n",
                   ++samples, frame, points[i][0], points[i][1], actual[0], actual[1], actual[2], expected & 0xffffff, pass ? "PASS" : "FAIL");
            if (!pass) fatal("compositor output mismatch");
        }
        XDestroyImage(image);
    }
    printf("RESULT PASS frames=12 samples=%u: opaque SHM + premultiplied alpha subsurface\n", samples);
    /* Leave the final fixture visible briefly for an independent capture. */
    wl_display_flush(d); sleep(3);
    for (unsigned i = 0; i < 24; ++i) wl_buffer_destroy(buffers[i]);
    wl_subsurface_destroy(sub); wl_surface_destroy(child);
    xdg_toplevel_destroy(top); xdg_surface_destroy(surface); wl_surface_destroy(parent);
    xdg_wm_base_destroy(wm); wl_shm_destroy(shm); wl_subcompositor_destroy(subcompositor);
    wl_compositor_destroy(compositor); wl_registry_destroy(registry);
    wl_display_disconnect(d); XCloseDisplay(x);
    return 0;
}
