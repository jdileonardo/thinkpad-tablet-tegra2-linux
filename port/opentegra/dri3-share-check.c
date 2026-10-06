/* Exercise server pixmap export, reimport, and bidirectional shared storage.
 * No Mesa context is used: this checks the Xorg DRI3/EXA bridge directly. */
#include <xcb/xcb.h>
#include <xcb/dri3.h>
#include <linux/dma-buf.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned samples;
static void fail(const char *where) { perror(where); exit(1); }
static void checked(xcb_connection_t *c, xcb_void_cookie_t cookie, const char *where)
{
    xcb_generic_error_t *e = xcb_request_check(c, cookie);
    if (e) {
        fprintf(stderr, "%s: X error=%u major=%u minor=%u resource=%#x\n",
                where, e->error_code, e->major_code, e->minor_code, e->resource_id);
        free(e); exit(1);
    }
}
static xcb_dri3_buffer_from_pixmap_reply_t *export_pixmap(xcb_connection_t *c,
                                                        xcb_pixmap_t pix, int *fd)
{
    xcb_generic_error_t *e = NULL;
    xcb_dri3_buffer_from_pixmap_reply_t *r = xcb_dri3_buffer_from_pixmap_reply(
        c, xcb_dri3_buffer_from_pixmap(c, pix), &e);
    if (!r || e || r->nfd != 1) {
        fprintf(stderr, "BufferFromPixmap failed: error=%u\n", e ? e->error_code : 0);
        free(e); free(r); exit(1);
    }
    *fd = xcb_dri3_buffer_from_pixmap_reply_fds(c, r)[0];
    return r;
}
static void cpu_sync(int fd, uint64_t flags)
{
    struct dma_buf_sync sync = { .flags = flags };
    int ret;
    do { ret = ioctl(fd, DMA_BUF_IOCTL_SYNC, &sync); } while (ret && errno == EINTR);
    if (ret) fail("DMA_BUF_IOCTL_SYNC");
}
static void expect(const char *stage, uint32_t actual, uint32_t expected)
{
    actual &= 0xffffff;
    expected &= 0xffffff;
    printf("sample=%u stage=%s actual=%06x expected=%06x %s\n", ++samples,
           stage, actual, expected, actual == expected ? "PASS" : "FAIL");
    if (actual != expected) exit(1);
}
static void read_pixel(xcb_connection_t *c, xcb_pixmap_t pix, unsigned x,
                       unsigned y, uint32_t color, const char *stage)
{
    xcb_generic_error_t *e = NULL;
    xcb_get_image_reply_t *r = xcb_get_image_reply(c,
        xcb_get_image(c, XCB_IMAGE_FORMAT_Z_PIXMAP, pix, x, y, 1, 1, ~0U), &e);
    if (!r || e || xcb_get_image_data_length(r) < 4) {
        fprintf(stderr, "GetImage failed: error=%u\n", e ? e->error_code : 0);
        free(e); free(r); exit(1);
    }
    uint32_t value;
    memcpy(&value, xcb_get_image_data(r), 4);
    expect(stage, value, color);
    free(r);
}
static void fill(xcb_connection_t *c, xcb_pixmap_t pix, xcb_gcontext_t gc,
                 unsigned width, unsigned height, uint32_t color)
{
    checked(c, xcb_change_gc_checked(c, gc, XCB_GC_FOREGROUND, &color), "ChangeGC");
    xcb_rectangle_t rect = { .width = width, .height = height };
    checked(c, xcb_poly_fill_rectangle_checked(c, pix, gc, 1, &rect), "FillRectangle");
}
static void test_size(xcb_connection_t *c, xcb_screen_t *s, unsigned width, unsigned height)
{
    xcb_pixmap_t pix = xcb_generate_id(c), alias = xcb_generate_id(c);
    xcb_gcontext_t gc = xcb_generate_id(c);
    checked(c, xcb_create_pixmap_checked(c, s->root_depth, pix, s->root, width, height), "CreatePixmap");
    checked(c, xcb_create_gc_checked(c, gc, pix, 0, NULL), "CreateGC");
    fill(c, pix, gc, width, height, 0x123456);
    int fd;
    xcb_dri3_buffer_from_pixmap_reply_t *r = export_pixmap(c, pix, &fd);
    printf("size=%ux%u stride=%u bytes=%u depth=%u bpp=%u\n", width, height,
           r->stride, r->size, r->depth, r->bpp);
    if (r->width != width || r->height != height || r->depth != 24 || r->bpp != 32 ||
        r->stride < width * 4 || r->stride % 16 || r->size < (uint64_t)r->stride * height)
        fail("invalid exported layout");
    uint32_t *map = mmap(NULL, r->size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    if (map == MAP_FAILED) fail("mmap");
    unsigned offset = (height - 1) * (r->stride / 4) + width - 1;
    cpu_sync(fd, DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ);
    expect("export-first", map[0], 0x123456);
    expect("export-last", map[offset], 0x123456);
    cpu_sync(fd, DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ);
    int imported_fd = dup(fd);
    if (imported_fd < 0) fail("dup");
    /* libxcb consumes the submitted FD. Our original FD remains owned here. */
    checked(c, xcb_dri3_pixmap_from_buffer_checked(c, alias, s->root, r->size,
        width, height, r->stride, r->depth, r->bpp, imported_fd), "PixmapFromBuffer");
    read_pixel(c, alias, width - 1, height - 1, 0x123456, "import-read");
    cpu_sync(fd, DMA_BUF_SYNC_START | DMA_BUF_SYNC_WRITE);
    map[0] = 0xffabcdef; map[offset] = 0xff654321;
    cpu_sync(fd, DMA_BUF_SYNC_END | DMA_BUF_SYNC_WRITE);
    read_pixel(c, pix, 0, 0, 0xabcdef, "CPU-write-original");
    read_pixel(c, alias, width - 1, height - 1, 0x654321, "CPU-write-alias");
    for (unsigned i = 0; i < 8; ++i) {
        uint32_t color = i % 2 ? 0x00dd77 : 0xbb22ee;
        xcb_pixmap_t target = i % 2 ? alias : pix;
        fill(c, target, gc, width, height, color);
        /* Export is the synchronization point the GL texture import uses. */
        int updated_fd;
        xcb_dri3_buffer_from_pixmap_reply_t *updated = export_pixmap(c, target, &updated_fd);
        close(updated_fd); free(updated);
        cpu_sync(fd, DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ);
        expect("X-update-shared-first", map[0], color);
        expect("X-update-shared-last", map[offset], color);
        cpu_sync(fd, DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ);
        read_pixel(c, i % 2 ? pix : alias, width / 2, height / 2, color, "X-update-other-pixmap");
    }
    munmap(map, r->size); close(fd); free(r);
    checked(c, xcb_free_pixmap_checked(c, alias), "FreeAlias");
    checked(c, xcb_free_gc_checked(c, gc), "FreeGC");
    checked(c, xcb_free_pixmap_checked(c, pix), "FreePixmap");
}
int main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    int screen;
    xcb_connection_t *c = xcb_connect(NULL, &screen);
    if (xcb_connection_has_error(c)) fail("xcb_connect");
    const xcb_setup_t *setup = xcb_get_setup(c);
    if (setup->image_byte_order != XCB_IMAGE_ORDER_LSB_FIRST) fail("unsupported image byte order");
    xcb_screen_iterator_t it = xcb_setup_roots_iterator(setup);
    for (int i = 0; i < screen; ++i) xcb_screen_next(&it);
    if (!it.rem || it.data->root_depth != 24) fail("unsupported screen depth");
    xcb_dri3_query_version_reply_t *v = xcb_dri3_query_version_reply(c,
        xcb_dri3_query_version(c, 1, 0), NULL);
    if (!v || v->major_version < 1) fail("DRI3 unavailable");
    printf("DRI3=%u.%u\n", v->major_version, v->minor_version); free(v);
    const unsigned sizes[][2] = {{8,8}, {63,37}, {640,480}};
    for (unsigned i = 0; i < sizeof(sizes)/sizeof(sizes[0]); ++i)
        test_size(c, it.data, sizes[i][0], sizes[i][1]);
    printf("RESULT PASS samples=%u sizes=3\n", samples);
    xcb_disconnect(c);
    return 0;
}
