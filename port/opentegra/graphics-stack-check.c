/* Report real GLES capabilities or read the active linear DRM scanout.
 * Neither mode sets a display mode or draws the expected capture pixels. */
#define _GNU_SOURCE
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <gbm.h>
#include <xf86drm.h>
#include <xf86drmMode.h>
#include <drm_fourcc.h>
#include <linux/dma-buf.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static _Noreturn void fail(const char *what)
{ perror(what); exit(1); }

static int has(const char *extensions, const char *name)
{
    size_t length = strlen(name);
    const char *p = extensions;
    while (p && (p = strstr(p, name))) {
        if ((p == extensions || p[-1] == ' ') && (!p[length] || p[length] == ' ')) return 1;
        p += length;
    }
    return 0;
}

static int capabilities(void)
{
    int fd = open("/dev/dri/renderD128", O_RDWR | O_CLOEXEC);
    if (fd < 0) fail("render node");
    struct gbm_device *gbm = gbm_create_device(fd);
    PFNEGLGETPLATFORMDISPLAYEXTPROC display = (void *)eglGetProcAddress("eglGetPlatformDisplayEXT");
    if (!gbm || !display) fail("GBM/platform display");
    EGLDisplay d = display(EGL_PLATFORM_GBM_KHR, gbm, NULL);
    EGLint major, minor;
    if (!eglInitialize(d, &major, &minor) || !eglBindAPI(EGL_OPENGL_ES_API)) fail("EGL initialize");
    const EGLint attributes[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
    EGLContext c = eglCreateContext(d, EGL_NO_CONFIG_KHR, EGL_NO_CONTEXT, attributes);
    if (c == EGL_NO_CONTEXT || !eglMakeCurrent(d, EGL_NO_SURFACE, EGL_NO_SURFACE, c)) fail("surfaceless context");
    const char *extensions = (const char *)glGetString(GL_EXTENSIONS);
    const char *renderer = (const char *)glGetString(GL_RENDERER);
    printf("vendor=%s renderer=%s version=%s glsl=%s EGL=%d.%d\n",
           glGetString(GL_VENDOR), renderer, glGetString(GL_VERSION),
           glGetString(GL_SHADING_LANGUAGE_VERSION), major, minor);
    printf("GL_EXTENSIONS=%s\nEGL_EXTENSIONS=%s\n", extensions, eglQueryString(d, EGL_EXTENSIONS));
    const char *required[] = {"GL_OES_texture_3D", "GL_EXT_unpack_subimage", "GL_EXT_read_format_bgra"};
    unsigned missing = 0;
    for (unsigned i = 0; i < sizeof(required) / sizeof(required[0]); ++i) {
        int supported = has(extensions, required[i]);
        printf("KWin_6.7.5_GLES_requirement %s=%s\n", required[i], supported ? "present" : "MISSING");
        missing += !supported;
    }
    printf("KWin_GLES_extension_gate=%s missing=%u (does not test its shader gate)\n",
           missing ? "FAIL" : "PASS", missing);
    int result = !renderer || strcmp(renderer, "Tegra") ? 2 : 0;
    eglMakeCurrent(d, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    eglDestroyContext(d, c); eglTerminate(d); gbm_device_destroy(gbm); close(fd);
    return result;
}

static int capture(const char *path)
{
    int fd = open("/dev/dri/card0", O_RDWR | O_CLOEXEC);
    if (fd < 0) fail("DRM node");
    drmModeRes *resources = drmModeGetResources(fd);
    if (!resources) fail("DRM resources");
    drmModeCrtc *active = NULL;
    for (int i = 0; i < resources->count_crtcs; ++i) {
        drmModeCrtc *crtc = drmModeGetCrtc(fd, resources->crtcs[i]);
        if (crtc && crtc->mode_valid && crtc->buffer_id) {
            if (active) fail("multiple active CRTCs");
            active = crtc;
        } else if (crtc) drmModeFreeCrtc(crtc);
    }
    if (!active) fail("active CRTC");
    drmModeFB2 *fb = drmModeGetFB2(fd, active->buffer_id);
    if (fb) printf("active framebuffer=%u size=%ux%u pitch=%u format=%08x modifier=%llu handles=%u,%u\n",
                   fb->fb_id, fb->width, fb->height, fb->pitches[0], fb->pixel_format,
                   (unsigned long long)fb->modifier, fb->handles[0], fb->handles[1]);
    int rgb565 = fb && (fb->pixel_format == DRM_FORMAT_RGB565 || fb->pixel_format == DRM_FORMAT_BGR565);
    int rgb8888 = fb && (fb->pixel_format == DRM_FORMAT_XRGB8888 || fb->pixel_format == DRM_FORMAT_ARGB8888 ||
                        fb->pixel_format == DRM_FORMAT_XBGR8888 || fb->pixel_format == DRM_FORMAT_ABGR8888);
    if (!fb || !fb->handles[0] || fb->handles[1] ||
        (!rgb565 && !rgb8888) ||
        ((fb->flags & DRM_MODE_FB_MODIFIERS) && fb->modifier != DRM_FORMAT_MOD_LINEAR))
        fail("supported linear single-plane framebuffer");
    int dmafd;
    if (drmPrimeHandleToFD(fd, fb->handles[0], DRM_CLOEXEC | DRM_RDWR, &dmafd)) fail("PRIME export");
    size_t length = (size_t)fb->pitches[0] * fb->height + fb->offsets[0];
    uint8_t *map = mmap(NULL, length, PROT_READ, MAP_SHARED, dmafd, 0);
    if (map == MAP_FAILED) fail("scanout mmap");
    struct dma_buf_sync sync = {.flags = DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ};
    if (ioctl(dmafd, DMA_BUF_IOCTL_SYNC, &sync)) fail("DMA sync start");
    FILE *output = fopen(path, "wb");
    if (!output) fail("capture output");
    fprintf(output, "P6\n%u %u\n255\n", fb->width, fb->height);
    for (uint32_t y = 0; y < fb->height; ++y) {
        uint8_t *row = map + fb->offsets[0] + (size_t)y * fb->pitches[0];
        for (uint32_t x = 0; x < fb->width; ++x) {
            uint8_t rgb[3];
            if (rgb565) {
                uint16_t pixel; memcpy(&pixel, row + x * 2, sizeof(pixel));
                rgb[0] = ((pixel >> 11) * 255 + 15) / 31;
                rgb[1] = (((pixel >> 5) & 63) * 255 + 31) / 63;
                rgb[2] = ((pixel & 31) * 255 + 15) / 31;
            } else {
                uint32_t pixel; memcpy(&pixel, row + x * 4, sizeof(pixel));
                rgb[0] = pixel >> 16; rgb[1] = pixel >> 8; rgb[2] = pixel;
            }
            if (fb->pixel_format == DRM_FORMAT_BGR565 || fb->pixel_format == DRM_FORMAT_XBGR8888 ||
                fb->pixel_format == DRM_FORMAT_ABGR8888) {
                uint8_t swap = rgb[0]; rgb[0] = rgb[2]; rgb[2] = swap;
            }
            if (fwrite(rgb, 1, 3, output) != 3) fail("capture write");
        }
    }
    if (fclose(output)) fail("capture close");
    sync.flags = DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ;
    if (ioctl(dmafd, DMA_BUF_IOCTL_SYNC, &sync)) fail("DMA sync end");
    printf("capture=%s CRTC=%u framebuffer=%u size=%ux%u pitch=%u format=%08x modifier=%llu\n",
           path, active->crtc_id, fb->fb_id, fb->width, fb->height, fb->pitches[0],
           fb->pixel_format, (unsigned long long)fb->modifier);
    munmap(map, length); close(dmafd);
    drmCloseBufferHandle(fd, fb->handles[0]); drmModeFreeFB2(fb);
    drmModeFreeCrtc(active); drmModeFreeResources(resources); close(fd);
    return 0;
}

int main(int argc, char **argv)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    if (argc == 2 && !strcmp(argv[1], "--capabilities")) return capabilities();
    if (argc == 3 && !strcmp(argv[1], "--capture")) return capture(argv[2]);
    fprintf(stderr, "Usage: graphics-stack-check --capabilities | --capture OUTPUT.ppm\n");
    return 1;
}
