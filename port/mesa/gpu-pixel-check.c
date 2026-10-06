/* Physical-device GLES2 drawing check; blue clear and red shader triangle. */
#include <EGL/egl.h>
#include <GLES2/gl2.h>
#include <gbm.h>
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static void fail(const char *what)
{
    fprintf(stderr, "%s: EGL=0x%x GL=0x%x\n", what, eglGetError(), glGetError());
    exit(1);
}

static GLuint shader(GLenum type, const char *source)
{
    GLuint object = glCreateShader(type);
    GLint status;
    glShaderSource(object, 1, &source, NULL);
    glCompileShader(object);
    glGetShaderiv(object, GL_COMPILE_STATUS, &status);
    if (!status) {
        char log[2048];
        glGetShaderInfoLog(object, sizeof(log), NULL, log);
        fprintf(stderr, "%s\n", log);
        fail("shader compile");
    }
    return object;
}

int main(int argc, char **argv)
{
    int show_window = 0, benchmark = 0, constants = 0, uniforms = 0;
    int arithmetic = 0, textured = 0, blending = 0, width = 32, height = 32, texture_size = 2;
    for (int i = 1; i < argc; ++i) {
        if (!strcmp(argv[i], "--x11")) show_window = 1;
        else if (!strcmp(argv[i], "--benchmark")) benchmark = 1;
        else if (!strcmp(argv[i], "--constants")) constants = 1;
        else if (!strcmp(argv[i], "--uniforms")) uniforms = 1;
        else if (!strcmp(argv[i], "--arithmetic")) arithmetic = 1;
        else if (!strcmp(argv[i], "--texture")) textured = 1;
        else if (!strcmp(argv[i], "--blend")) blending = 1;
        else if (sscanf(argv[i], "--texture-size=%d", &texture_size) == 1) {}
        else if (sscanf(argv[i], "--size=%dx%d", &width, &height) != 2) {
            fprintf(stderr, "Unknown argument: %s\n", argv[i]);
            return 1;
        }
    }
    if (constants + uniforms + arithmetic + textured + blending > 1 ||
        (show_window && (textured || arithmetic || blending))) return 1;
    if (width < 8 || height < 8 || width > 2048 || height > 2048) return 1;
    if (texture_size < 2 || texture_size > 512) return 1;
    int fd = open("/dev/dri/renderD128", O_RDWR | O_CLOEXEC);
    if (fd < 0) { perror("render device"); return 1; }
    struct gbm_device *gbm = gbm_create_device(fd);
    if (!gbm) fail("GBM device");
    Display *xdisplay = show_window ? XOpenDisplay(NULL) : NULL;
    if (show_window && !xdisplay) fail("X display");
    EGLDisplay display = eglGetDisplay((EGLNativeDisplayType)(show_window ? (void *)xdisplay : (void *)gbm));
    EGLint major, minor, count;
    if (!eglInitialize(display, &major, &minor)) fail("EGL initialize");
    if (!eglBindAPI(EGL_OPENGL_ES_API)) fail("bind GLES");
    const EGLint config_attrs[] = { EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
                                   EGL_SURFACE_TYPE, show_window ? EGL_WINDOW_BIT : 0,
                                   EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_NONE };
    EGLConfig config;
    if (!eglChooseConfig(display, config_attrs, &config, 1, &count) || count != 1)
        fail("EGL config");
    const EGLint context_attrs[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
    EGLContext context = eglCreateContext(display, config, EGL_NO_CONTEXT, context_attrs);
    if (context == EGL_NO_CONTEXT) fail("EGL context");
    Window window = 0;
    EGLSurface surface = EGL_NO_SURFACE;
    if (show_window) {
        EGLint visual_id;
        if (!eglGetConfigAttrib(display, config, EGL_NATIVE_VISUAL_ID, &visual_id)) fail("X visual");
        XVisualInfo visual_template = { .visualid = visual_id };
        int visuals;
        XVisualInfo *visual = XGetVisualInfo(xdisplay, VisualIDMask, &visual_template, &visuals);
        if (!visual || visuals < 1) fail("X visual lookup");
        XSetWindowAttributes attrs = { .colormap = XCreateColormap(xdisplay, RootWindow(xdisplay, visual->screen), visual->visual, AllocNone),
                                      .event_mask = ExposureMask | StructureNotifyMask };
        window = XCreateWindow(xdisplay, RootWindow(xdisplay, visual->screen), 50, 50, 400, 300, 0,
                               visual->depth, InputOutput, visual->visual, CWColormap | CWEventMask, &attrs);
        XFree(visual);
        XStoreName(xdisplay, window, "Indigo hardware GPU: Grate / Tegra");
        XMapWindow(xdisplay, window);
        XSync(xdisplay, False);
        surface = eglCreateWindowSurface(display, config, window, NULL);
        if (surface == EGL_NO_SURFACE) fail("window surface");
    }
    if (!eglMakeCurrent(display, surface, surface, context)) fail("make current");
    const char *renderer = (const char *)glGetString(GL_RENDERER);
    printf("EGL=%d.%d vendor=%s renderer=%s version=%s\n", major, minor,
           glGetString(GL_VENDOR), renderer, glGetString(GL_VERSION));
    fflush(stdout);
    GLuint texture, framebuffer;
    glGenTextures(1, &texture);
    glBindTexture(GL_TEXTURE_2D, texture);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, NULL);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glGenFramebuffers(1, &framebuffer);
    glBindFramebuffer(GL_FRAMEBUFFER, framebuffer);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, texture, 0);
    GLenum framebuffer_status = glCheckFramebufferStatus(GL_FRAMEBUFFER);
    if (framebuffer_status != GL_FRAMEBUFFER_COMPLETE) {
        fprintf(stderr, "framebuffer_status=0x%x\n", framebuffer_status);
        fail("framebuffer");
    }
    glViewport(0, 0, width, height);
    glClearColor(0, 0, 1, 1);
    glClear(GL_COLOR_BUFFER_BIT);
    /* Attribute-only shaders isolate primitive drawing from immediate support. */
    printf("shader_mode=%s\n", constants ? "constants" : uniforms ? "uniforms" :
           arithmetic ? "arithmetic" : textured ? "texture" : blending ? "blend" : "attributes");
    GLuint vs = shader(GL_VERTEX_SHADER, textured ?
        "attribute vec4 position; attribute vec4 color; varying vec2 uv; void main() { gl_Position=position; uv=color.xy; }" : constants ?
        "attribute vec2 position; void main() { gl_Position=vec4(position,0.0,1.0); }" :
        "attribute vec4 position; attribute vec4 color; varying vec4 vcolor; void main() { gl_Position=position; vcolor=color; }");
    GLuint fs = shader(GL_FRAGMENT_SHADER, textured ?
        "precision mediump float; varying vec2 uv; uniform sampler2D source; void main() { gl_FragColor=texture2D(source,uv); }" : uniforms ?
        "precision mediump float; uniform vec4 tint; void main() { gl_FragColor=tint; }" : arithmetic ?
        "precision mediump float; varying vec4 vcolor; uniform vec4 scale,bias; void main() { gl_FragColor=vcolor*scale+bias; }" : constants ?
        "precision mediump float; void main() { gl_FragColor=vec4(1.0,0.0,0.0,1.0); }" :
        "precision mediump float; varying vec4 vcolor; void main() { gl_FragColor=vcolor; }");
    GLuint program = glCreateProgram();
    glAttachShader(program, vs);
    glAttachShader(program, fs);
    glBindAttribLocation(program, 0, "position");
    glBindAttribLocation(program, 1, "color");
    glLinkProgram(program);
    GLint status;
    glGetProgramiv(program, GL_LINK_STATUS, &status);
    if (!status) fail("program link");
    GLfloat vertices[] = {
        -0.8f,-0.8f,0,1, 1,0,0,1,
         0.8f,-0.8f,0,1, 1,0,0,1,
         0.0f, 0.8f,0,1, 1,0,0,1
    };
    if (blending)
        for (int i = 0; i < 3; ++i) vertices[i * 8 + 7] = 0.5f;
    const GLfloat quad[] = {
        -0.8f,-0.8f,0,1, 0,0,0,0,
         0.8f,-0.8f,0,1, 1,0,0,0,
        -0.8f, 0.8f,0,1, 0,1,0,0,
         0.8f, 0.8f,0,1, 1,1,0,0,
    };
    GLuint buffer;
    glGenBuffers(1, &buffer);
    glBindBuffer(GL_ARRAY_BUFFER, buffer);
    glBufferData(GL_ARRAY_BUFFER, textured ? sizeof(quad) : sizeof(vertices),
                 textured ? quad : vertices, GL_STATIC_DRAW);
    glVertexAttribPointer(0, 4, GL_FLOAT, GL_FALSE, 8 * sizeof(GLfloat), NULL);
    glVertexAttribPointer(1, 4, GL_FLOAT, GL_FALSE, 8 * sizeof(GLfloat), (void *)(4 * sizeof(GLfloat)));
    glEnableVertexAttribArray(0);
    glEnableVertexAttribArray(1);
    glUseProgram(program);
    if (uniforms) glUniform4f(glGetUniformLocation(program, "tint"), 1, 0, 0, 1);
    if (arithmetic) {
        glUniform4f(glGetUniformLocation(program, "scale"), 0.25f, 0.25f, 0.25f, 0.25f);
        glUniform4f(glGetUniformLocation(program, "bias"), 0.25f, 0.25f, 0.75f, 0.75f);
    }
    if (blending) {
        glEnable(GL_BLEND);
        glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA);
    }
    GLuint sampled_texture = 0;
    if (textured) {
        const unsigned char colors[4][4] = {{255,0,0,255}, {0,255,0,255},
                                          {0,0,255,255}, {255,255,0,255}};
        unsigned char *pixels = malloc((size_t)texture_size * texture_size * 4);
        if (!pixels) fail("texture pixels");
        for (int y = 0; y < texture_size; ++y)
            for (int x = 0; x < texture_size; ++x)
                memcpy(pixels + (y * texture_size + x) * 4,
                       colors[(x >= texture_size / 2) + 2 * (y >= texture_size / 2)], 4);
        glGenTextures(1, &sampled_texture);
        glBindTexture(GL_TEXTURE_2D, sampled_texture);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, texture_size, texture_size, 0, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
        free(pixels);
        printf("texture_size=%dx%d\n", texture_size, texture_size);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
        glUniform1i(glGetUniformLocation(program, "source"), 0);
    }
    glDrawArrays(textured ? GL_TRIANGLE_STRIP : GL_TRIANGLES, 0, textured ? 4 : 3);
    glFinish();
    if (benchmark) {
        struct timespec started, now;
        clock_gettime(CLOCK_MONOTONIC, &started);
        unsigned frames = 0;
        double elapsed;
        do {
            glClear(GL_COLOR_BUFFER_BIT);
            glDrawArrays(textured ? GL_TRIANGLE_STRIP : GL_TRIANGLES, 0, textured ? 4 : 3);
            glFinish();
            ++frames;
            clock_gettime(CLOCK_MONOTONIC, &now);
            elapsed = now.tv_sec - started.tv_sec + (now.tv_nsec - started.tv_nsec) / 1e9;
        } while (elapsed < 3.0);
        printf("simple_triangle_size=%dx%d frames=%u seconds=%.6f fps=%.2f\n",
               width, height, frames, elapsed, frames / elapsed);
    }
    unsigned char center[4], corner[4];
    glReadPixels(width / 2, height / 2, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, center);
    glReadPixels(0, 0, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, corner);
    if (glGetError() != GL_NO_ERROR) fail("draw/readback");
    printf("center=%u,%u,%u,%u corner=%u,%u,%u,%u\n", center[0], center[1], center[2], center[3],
           corner[0], corner[1], corner[2], corner[3]);
    int correct = center[0] > 240 && center[1] < 15 && center[2] < 15 && center[3] > 240 &&
                  corner[0] < 15 && corner[1] < 15 && corner[2] > 240 && corner[3] > 240;
    if (arithmetic || blending) {
        const int expected[4] = {128, arithmetic ? 64 : 0, arithmetic ? 191 : 128, 255};
        correct = corner[0] < 15 && corner[1] < 15 && corner[2] > 240 && corner[3] > 240;
        for (int channel = 0; channel < 4; ++channel)
            if (abs((int)center[channel] - expected[channel]) > 14) correct = 0;
    }
    if (textured) {
        const unsigned char expected[4][4] = {{255,0,0,255},{0,255,0,255},
                                            {0,0,255,255},{255,255,0,255}};
        correct = corner[0] < 15 && corner[1] < 15 && corner[2] > 240 && corner[3] > 240;
        for (int i = 0; i < 4; ++i) {
            unsigned char sampled[4];
            glReadPixels((i & 1) ? width * 3 / 4 : width / 4,
                         (i & 2) ? height * 3 / 4 : height / 4,
                         1, 1, GL_RGBA, GL_UNSIGNED_BYTE, sampled);
            printf("texture_sample%d=%u,%u,%u,%u\n", i, sampled[0], sampled[1], sampled[2], sampled[3]);
            for (int channel = 0; channel < 4; ++channel)
                if (abs((int)sampled[channel] - expected[i][channel]) > 14) correct = 0;
        }
        if (glGetError() != GL_NO_ERROR) fail("texture readback");
    }
    int hardware = renderer && !strcmp(renderer, "Tegra");
    printf("pixel_check=%s hardware_renderer=%s\n", correct ? "PASS" : "FAIL", hardware ? "YES" : "NO");
    fflush(stdout);
    if (show_window && correct) {
        glBindFramebuffer(GL_FRAMEBUFFER, 0);
        glViewport(0, 0, 400, 300);
        glClear(GL_COLOR_BUFFER_BIT);
        glDrawArrays(GL_TRIANGLES, 0, 3);
        glFinish();
        unsigned char shown[4];
        glReadPixels(200, 150, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, shown);
        printf("window_center=%u,%u,%u,%u\n", shown[0], shown[1], shown[2], shown[3]);
        correct = shown[0] > 240 && shown[1] < 15 && shown[2] < 15;
        if (!eglSwapBuffers(display, surface)) fail("present window");
        fflush(stdout);
        sleep(20);
    }
    eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    if (surface != EGL_NO_SURFACE) eglDestroySurface(display, surface);
    eglDestroyContext(display, context);
    eglTerminate(display);
    if (show_window) { XDestroyWindow(xdisplay, window); XCloseDisplay(xdisplay); }
    gbm_device_destroy(gbm);
    close(fd);
    return correct ? (hardware ? 0 : 2) : 1;
}
