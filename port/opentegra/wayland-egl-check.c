/* A real hardware Wayland EGL client. Independent DRM capture checks scanout. */
#define _GNU_SOURCE
#include <wayland-client.h>
#include <wayland-egl.h>
#include "xdg-shell-client-protocol.h"
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static struct wl_compositor *compositor;
static struct xdg_wm_base *wm;
static int configured, frame_done, width = 640, height = 480;
static _Noreturn void fail(const char *what)
{ fprintf(stderr, "FAIL %s EGL=%x GL=%x\n", what, eglGetError(), glGetError()); exit(1); }
static void ping(void *data, struct xdg_wm_base *base, uint32_t serial)
{ (void)data; xdg_wm_base_pong(base, serial); }
static const struct xdg_wm_base_listener wm_listener = {.ping = ping};
static void global(void *data, struct wl_registry *registry, uint32_t id,
                   const char *interface, uint32_t version)
{
    (void)data;
    if (!strcmp(interface, "wl_compositor"))
        compositor = wl_registry_bind(registry, id, &wl_compositor_interface, version < 4 ? version : 4);
    else if (!strcmp(interface, "xdg_wm_base")) {
        wm = wl_registry_bind(registry, id, &xdg_wm_base_interface, 1);
        xdg_wm_base_add_listener(wm, &wm_listener, NULL);
    }
}
static void removed(void *data, struct wl_registry *registry, uint32_t id)
{ (void)data; (void)registry; (void)id; }
static const struct wl_registry_listener registry_listener = {.global = global, .global_remove = removed};
static void configure(void *data, struct xdg_surface *surface, uint32_t serial)
{ (void)data; xdg_surface_ack_configure(surface, serial); configured = 1; }
static const struct xdg_surface_listener surface_listener = {.configure = configure};
static void top_configure(void *data, struct xdg_toplevel *top, int32_t w, int32_t h,
                          struct wl_array *states)
{ (void)data; (void)top; (void)states; if (w > 0) width = w; if (h > 0) height = h; }
static void top_close(void *data, struct xdg_toplevel *top)
{ (void)data; (void)top; fail("toplevel closed"); }
static const struct xdg_toplevel_listener top_listener = {.configure = top_configure, .close = top_close};
static void callback_done(void *data, struct wl_callback *callback, uint32_t ms)
{ (void)data; (void)ms; frame_done = 1; wl_callback_destroy(callback); }
static const struct wl_callback_listener frame_listener = {.done = callback_done};

static GLuint shader(GLenum type, const char *source)
{
    GLuint object = glCreateShader(type);
    GLint ok;
    glShaderSource(object, 1, &source, NULL); glCompileShader(object);
    glGetShaderiv(object, GL_COMPILE_STATUS, &ok);
    if (!ok) fail("drawing shader compile");
    return object;
}

int main(int argc, char **argv)
{
    int draw = 0, rgb565 = 0;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--draw")) draw = 1;
        else if (!strcmp(argv[i], "--rgb565")) rgb565 = 1;
        else fail("Usage: wayland-egl-check [--draw] [--rgb565]");
    }
    setvbuf(stdout, NULL, _IONBF, 0);
    struct wl_display *wl = wl_display_connect(NULL);
    if (!wl) fail("Wayland connection");
    struct wl_registry *registry = wl_display_get_registry(wl);
    wl_registry_add_listener(registry, &registry_listener, NULL);
    if (wl_display_roundtrip(wl) < 0 || !wm || !compositor) fail("Wayland globals");
    struct wl_surface *surface = wl_compositor_create_surface(compositor);
    struct xdg_surface *xdg = xdg_wm_base_get_xdg_surface(wm, surface);
    xdg_surface_add_listener(xdg, &surface_listener, NULL);
    struct xdg_toplevel *top = xdg_surface_get_toplevel(xdg);
    xdg_toplevel_add_listener(top, &top_listener, NULL);
    xdg_toplevel_set_title(top, "Indigo hardware Wayland EGL check");
    xdg_toplevel_set_fullscreen(top, NULL); wl_surface_commit(surface);
    while (!configured) if (wl_display_dispatch(wl) < 0) fail("configure");
    struct wl_region *region = wl_compositor_create_region(compositor);
    wl_region_add(region, 0, 0, width, height);
    wl_surface_set_opaque_region(surface, region); wl_region_destroy(region);
    PFNEGLGETPLATFORMDISPLAYEXTPROC get_display = (void *)eglGetProcAddress("eglGetPlatformDisplayEXT");
    if (!get_display) fail("platform display entry point");
    EGLDisplay d = get_display(EGL_PLATFORM_WAYLAND_EXT, wl, NULL);
    EGLint major, minor, count;
    EGLConfig config;
    const EGLint attrs[] = {EGL_SURFACE_TYPE, EGL_WINDOW_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
                            EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 0, EGL_NONE};
    if (!eglInitialize(d, &major, &minor) || !eglBindAPI(EGL_OPENGL_ES_API) ||
        !eglChooseConfig(d, attrs, &config, 1, &count) || count != 1) fail("Wayland EGL setup");
    if (rgb565) {
        const EGLint low_attrs[] = {EGL_SURFACE_TYPE, EGL_WINDOW_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
                                   EGL_RED_SIZE, 5, EGL_GREEN_SIZE, 6, EGL_BLUE_SIZE, 5, EGL_ALPHA_SIZE, 0, EGL_NONE};
        EGLConfig configs[512]; EGLint available;
        if (!eglChooseConfig(d, low_attrs, configs, 512, &available)) fail("RGB565 configs");
        config = NULL;
        for (int i = 0; i < available; ++i) {
            EGLint r, g, b, a;
            eglGetConfigAttrib(d, configs[i], EGL_RED_SIZE, &r);
            eglGetConfigAttrib(d, configs[i], EGL_GREEN_SIZE, &g);
            eglGetConfigAttrib(d, configs[i], EGL_BLUE_SIZE, &b);
            eglGetConfigAttrib(d, configs[i], EGL_ALPHA_SIZE, &a);
            if (r == 5 && g == 6 && b == 5 && a == 0) { config = configs[i]; break; }
        }
        if (!config) fail("exact RGB565 config");
    }
    const EGLint context_attrs[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
    EGLContext context = eglCreateContext(d, config, EGL_NO_CONTEXT, context_attrs);
    struct wl_egl_window *window = wl_egl_window_create(surface, width, height);
    EGLSurface target = eglCreateWindowSurface(d, config, (EGLNativeWindowType)window, NULL);
    if (!window || context == EGL_NO_CONTEXT || target == EGL_NO_SURFACE ||
        !eglMakeCurrent(d, target, target, context)) fail("Wayland EGL window context");
    const char *renderer = (const char *)glGetString(GL_RENDERER);
    EGLint buffer_bits; eglGetConfigAttrib(d, config, EGL_BUFFER_SIZE, &buffer_bits);
    printf("Wayland client vendor=%s renderer=%s version=%s EGL=%d.%d size=%dx%d buffer_bits=%d\n",
           glGetString(GL_VENDOR), renderer, glGetString(GL_VERSION), major, minor, width, height, buffer_bits);
    if (!renderer || strcmp(renderer, "Tegra")) fail("expected hardware Tegra renderer");
    GLuint program = 0, vertices = 0, indices = 0;
    if (draw) {
        program = glCreateProgram();
        glAttachShader(program, shader(GL_VERTEX_SHADER,
            "attribute vec4 vertex; uniform mat4 matrix; void main(){gl_Position=matrix*vertex;}"));
        glAttachShader(program, shader(GL_FRAGMENT_SHADER,
            "precision mediump float; uniform vec4 color; void main(){gl_FragColor=color;}"));
        glBindAttribLocation(program, 0, "vertex"); glLinkProgram(program);
        GLint ok; glGetProgramiv(program, GL_LINK_STATUS, &ok);
        if (!ok) fail("drawing shader link");
        glUseProgram(program);
        const GLfloat matrix[16] = {2.f/width,0,0,0, 0,2.f/height,0,0,
                                     0,0,1,0, -1,-1,0,1};
        glUniformMatrix4fv(glGetUniformLocation(program, "matrix"), 1, GL_FALSE, matrix);
        const GLfloat quad[] = {0,0,0,1, width/2.f,0,0,1, 0,height,0,1, width/2.f,height,0,1};
        glGenBuffers(1, &vertices); glBindBuffer(GL_ARRAY_BUFFER, vertices);
        glBufferData(GL_ARRAY_BUFFER, sizeof(quad), quad, GL_STATIC_DRAW);
        const GLushort order[] = {0,1,2,2,1,3};
        glGenBuffers(1, &indices); glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, indices);
        glBufferData(GL_ELEMENT_ARRAY_BUFFER, sizeof(order), order, GL_STATIC_DRAW);
        glEnableVertexAttribArray(0); glViewport(0, 0, width, height);
    }
    unsigned samples = 0;
    for (unsigned frame = 0; frame < 3; ++frame) {
        const unsigned left[3] = {frame == 1 ? 0 : 255, frame == 1 ? 255 : 0, 0};
        const unsigned right[3] = {frame == 1 ? 255 : 0, frame == 1 ? 255 : 0, frame == 1 ? 0 : 255};
        glDisable(GL_SCISSOR_TEST);
        glClearColor(right[0] / 255.f, right[1] / 255.f, right[2] / 255.f, 1);
        glClear(GL_COLOR_BUFFER_BIT);
        if (draw) {
            glVertexAttribPointer(0, frame ? 2 : 4, GL_FLOAT, GL_FALSE, 4 * sizeof(GLfloat), NULL);
            glUniform4f(glGetUniformLocation(program, "color"), left[0]/255.f, left[1]/255.f, left[2]/255.f, 1);
            if (frame == 2) glDrawElements(GL_TRIANGLES, 6, GL_UNSIGNED_SHORT, NULL);
            else glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
            printf("draw frame=%u matrix=orthographic attribute_components=%u indexed=%u\n", frame, frame ? 2 : 4, frame == 2);
        } else {
            glEnable(GL_SCISSOR_TEST); glScissor(0, 0, width / 2, height);
            glClearColor(left[0] / 255.f, left[1] / 255.f, left[2] / 255.f, 1);
            glClear(GL_COLOR_BUFFER_BIT); glDisable(GL_SCISSOR_TEST);
        }
        for (unsigned side = 0; side < 2; ++side) {
            unsigned char rgba[4];
            glReadPixels(side ? width * 3 / 4 : width / 4, height / 2, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, rgba);
            const unsigned *expected = side ? right : left;
            printf("frame=%u side=%u GPU_rgb=%u,%u,%u expected=%u,%u,%u\n", frame, side,
                   rgba[0], rgba[1], rgba[2], expected[0], expected[1], expected[2]);
            for (unsigned j = 0; j < 3; ++j)
                if (abs((int)rgba[j] - (int)expected[j]) > 2) fail("client GPU readback");
            samples++;
        }
        frame_done = 0;
        wl_callback_add_listener(wl_surface_frame(surface), &frame_listener, NULL);
        if (glGetError() || !eglSwapBuffers(d, target)) fail("Wayland swap");
        while (!frame_done) if (wl_display_dispatch(wl) < 0) fail("Wayland frame callback");
        usleep(frame ? 500000 : 2000000);
    }
    printf("READY_CAPTURE frames=3 local_samples=%u final=left-red,right-blue\n", samples);
    wl_display_flush(wl); sleep(5);
    eglMakeCurrent(d, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    eglDestroySurface(d, target); eglDestroyContext(d, context); eglTerminate(d);
    wl_egl_window_destroy(window); xdg_toplevel_destroy(top); xdg_surface_destroy(xdg);
    wl_surface_destroy(surface); xdg_wm_base_destroy(wm); wl_compositor_destroy(compositor);
    wl_registry_destroy(registry); wl_display_disconnect(wl);
    puts("RESULT PASS hardware Wayland EGL swaps and local GPU samples; verify independent scanout separately");
    return 0;
}
