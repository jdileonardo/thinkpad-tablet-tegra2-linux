/* Compare actual Xorg window pixels with GPU rendering, including orientation. */
#include <EGL/egl.h>
#include <GLES2/gl2.h>
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static _Noreturn void fail(const char *stage)
{
    fprintf(stderr, "FAIL %s EGL=0x%x GL=0x%x\n", stage, eglGetError(), glGetError());
    exit(1);
}

static GLuint shader(GLenum type, const char *source)
{
    GLuint object = glCreateShader(type);
    GLint ok;
    glShaderSource(object, 1, &source, NULL);
    glCompileShader(object);
    glGetShaderiv(object, GL_COMPILE_STATUS, &ok);
    if (!ok) fail("shader compile");
    return object;
}

static unsigned channel(unsigned long pixel, unsigned long mask)
{
    if (!mask) return 0;
    while (!(mask & 1)) { mask >>= 1; pixel >>= 1; }
    return (pixel & mask) * 255 / mask;
}

int main(int argc, char **argv)
{
    int width = 256, height = 256;
    int gpu_readback = argc == 3 && !strcmp(argv[2], "--gpu-readback");
    if (argc > 3 || (argc == 3 && !gpu_readback) ||
        (argc >= 2 && sscanf(argv[1], "%dx%d", &width, &height) != 2) ||
        width < 32 || height < 32 || width > 2048 || height > 2048)
        return 1;
    Display *x = XOpenDisplay(NULL);
    if (!x) fail("XOpenDisplay");
    EGLDisplay d = eglGetDisplay((EGLNativeDisplayType)x);
    EGLint major, minor, count, visual_id;
    EGLConfig config;
    const EGLint attrs[] = { EGL_SURFACE_TYPE, EGL_WINDOW_BIT,
        EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
        EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_NONE };
    if (!eglInitialize(d, &major, &minor) || !eglBindAPI(EGL_OPENGL_ES_API) ||
        !eglChooseConfig(d, attrs, &config, 1, &count) || count != 1 ||
        !eglGetConfigAttrib(d, config, EGL_NATIVE_VISUAL_ID, &visual_id))
        fail("EGL setup");
    XVisualInfo template = { .visualid = visual_id };
    int nvisuals;
    XVisualInfo *v = XGetVisualInfo(x, VisualIDMask, &template, &nvisuals);
    if (!v || nvisuals < 1) fail("visual");
    XSetWindowAttributes wa = {
        .colormap = XCreateColormap(x, RootWindow(x, v->screen), v->visual, AllocNone),
        .override_redirect = True,
    };
    Window w = XCreateWindow(x, RootWindow(x, v->screen), 0, 0, width, height,
        0, v->depth, InputOutput, v->visual, CWColormap | CWOverrideRedirect, &wa);
    XMapRaised(x, w);
    XSync(x, False);
    const EGLint ca[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
    EGLContext c = eglCreateContext(d, config, EGL_NO_CONTEXT, ca);
    EGLSurface s = eglCreateWindowSurface(d, config, w, NULL);
    if (c == EGL_NO_CONTEXT || s == EGL_NO_SURFACE || !eglMakeCurrent(d, s, s, c))
        fail("window context");
    const char *renderer = (const char *)glGetString(GL_RENDERER);
    printf("renderer=%s EGL=%d.%d size=%dx%d\n", renderer, major, minor, width, height);
    fflush(stdout);
    if (!renderer || strcmp(renderer, "Tegra")) return 2;
    GLuint p = glCreateProgram();
    glAttachShader(p, shader(GL_VERTEX_SHADER,
        "attribute vec2 pos; void main(){gl_Position=vec4(pos,0.0,1.0);}"));
    glAttachShader(p, shader(GL_FRAGMENT_SHADER,
        "precision mediump float; uniform vec4 color; void main(){gl_FragColor=color;}"));
    glBindAttribLocation(p, 0, "pos");
    glLinkProgram(p);
    GLint linked;
    glGetProgramiv(p, GL_LINK_STATUS, &linked);
    if (!linked) fail("program link");
    glUseProgram(p);
    const GLfloat vertices[] = {-1,-1, 1,-1, 1,0, -1,-1, 1,0, -1,0};
    GLuint buffer;
    glGenBuffers(1, &buffer);
    glBindBuffer(GL_ARRAY_BUFFER, buffer);
    glBufferData(GL_ARRAY_BUFFER, sizeof(vertices), vertices, GL_STATIC_DRAW);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, NULL);
    glEnableVertexAttribArray(0);
    glViewport(0, 0, width, height);
    int failures = 0;
    for (int frame = 0; frame < 3; frame++) {
        glDisable(GL_BLEND);
        glClearColor(0, 0, 1, 1);
        glClear(GL_COLOR_BUFFER_BIT);
        if (frame == 2) {
            glEnable(GL_BLEND);
            glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE,
                                GL_ONE_MINUS_SRC_ALPHA);
        }
        glUniform4f(glGetUniformLocation(p, "color"), frame == 1 ? 0 : 1,
                    frame == 1 ? 1 : 0, 0, frame == 2 ? 0.5 : 1);
        glDrawArrays(GL_TRIANGLES, 0, 6);
        glFinish();
        if (gpu_readback) {
            unsigned char gpu[4];
            glReadPixels(width / 2, height / 8, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, gpu);
            printf("frame=%d GPU_bottom_rgba=%u,%u,%u,%u\n", frame,
                   gpu[0], gpu[1], gpu[2], gpu[3]);
        }
        if (glGetError() || !eglSwapBuffers(d, s)) fail("draw or swap");
        /* Wait for Present's asynchronous copy before reading through Xorg. */
        usleep(200000);
        XSync(x, False);
        XImage *image = XGetImage(x, w, 0, 0, width, height, AllPlanes, ZPixmap);
        if (!image) fail("XGetImage");
        for (int sample = 0; sample < 2; sample++) {
            unsigned long pixel = XGetPixel(image, width / 2,
                                            sample ? height * 7 / 8 : height / 8);
            unsigned actual[] = { channel(pixel, image->red_mask),
                channel(pixel, image->green_mask), channel(pixel, image->blue_mask) };
            int expected[3] = {0, 0, 255};
            if (sample) {
                expected[0] = frame == 1 ? 0 : frame == 2 ? 128 : 255;
                expected[1] = frame == 1 ? 255 : 0;
                expected[2] = frame == 2 ? 128 : 0;
            }
            int ok = 1;
            for (int k = 0; k < 3; k++)
                if (abs((int)actual[k] - expected[k]) > 2) ok = 0;
            failures += !ok;
            printf("frame=%d %s Xorg_rgb=%u,%u,%u expected=%d,%d,%d %s\n", frame,
                sample ? "bottom" : "top", actual[0], actual[1], actual[2],
                expected[0], expected[1], expected[2], ok ? "PASS" : "FAIL");
        }
        XDestroyImage(image);
        fflush(stdout);
    }
    eglMakeCurrent(d, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    eglDestroySurface(d, s);
    eglDestroyContext(d, c);
    eglTerminate(d);
    XDestroyWindow(x, w);
    XFree(v);
    XCloseDisplay(x);
    printf("presentation_check=%s failures=%d\n", failures ? "FAIL" : "PASS", failures);
    return failures ? 1 : 0;
}
