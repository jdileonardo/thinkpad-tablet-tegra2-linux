/* Compare GL blending on real Grate hardware with the same softpipe program.
 * Covers draw ordering, shared edges, transparency, interpolation and textures.
 */
#include <EGL/egl.h>
#include <GLES2/gl2.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static GLuint program(const char *fragment)
{
    const char *vertex = "attribute vec2 pos; attribute vec4 color;"
        "varying vec4 c; void main(){gl_Position=vec4(pos,0.,1.);c=color;}";
    GLuint shaders[2], p = glCreateProgram();
    const char *sources[2] = {vertex, fragment};
    for (int i = 0; i < 2; ++i) {
        shaders[i] = glCreateShader(i ? GL_FRAGMENT_SHADER : GL_VERTEX_SHADER);
        glShaderSource(shaders[i], 1, &sources[i], NULL);
        glCompileShader(shaders[i]);
        GLint ok;
        glGetShaderiv(shaders[i], GL_COMPILE_STATUS, &ok);
        if (!ok) { fprintf(stderr, "COMPILE_FAIL\n"); exit(1); }
        glAttachShader(p, shaders[i]);
    }
    glBindAttribLocation(p, 0, "pos");
    glBindAttribLocation(p, 1, "color");
    glLinkProgram(p);
    GLint ok;
    glGetProgramiv(p, GL_LINK_STATUS, &ok);
    if (!ok) { fprintf(stderr, "LINK_FAIL\n"); exit(1); }
    for (int i = 0; i < 2; ++i) glDeleteShader(shaders[i]);
    return p;
}

static void vertices(GLuint buffer, const GLfloat *data, unsigned count)
{
    glBindBuffer(GL_ARRAY_BUFFER, buffer);
    glBufferData(GL_ARRAY_BUFFER, count * 6 * sizeof(GLfloat), data, GL_STREAM_DRAW);
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 6 * sizeof(GLfloat), NULL);
    glVertexAttribPointer(1, 4, GL_FLOAT, GL_FALSE, 6 * sizeof(GLfloat),
                          (void *)(2 * sizeof(GLfloat)));
    glEnableVertexAttribArray(0);
    glEnableVertexAttribArray(1);
}

static void triangle(GLfloat *data, float r, float g, float b, float a)
{
    const GLfloat positions[6] = {-1,-1, 1,-1, 0,1};
    for (int i = 0; i < 3; ++i) {
        data[i * 6] = positions[i * 2];
        data[i * 6 + 1] = positions[i * 2 + 1];
        data[i * 6 + 2] = r; data[i * 6 + 3] = g;
        data[i * 6 + 4] = b; data[i * 6 + 5] = a;
    }
}

static void sample(const char *name)
{
    for (int y = 0; y < 3; ++y)
        for (int x = 0; x < 3; ++x) {
            unsigned char rgba[4];
            glReadPixels(16 + x * 16, 16 + y * 16, 1, 1,
                         GL_RGBA, GL_UNSIGNED_BYTE, rgba);
            printf("%s_%d_%d %u,%u,%u,%u err=0x%x\n", name, x, y,
                   rgba[0], rgba[1], rgba[2], rgba[3], glGetError());
        }
}

static void state_cases(GLuint color, GLuint buffer)
{
    /* Use the same linked program and FBO for state changes and cache reuse.
     * A full-screen quad makes every sampled pixel exercise the equation. */
    const GLfloat quad[] = {-1,-1, .65,.35,.2,.4, 1,-1, .65,.35,.2,.4,
                           -1,1, .65,.35,.2,.4, 1,1, .65,.35,.2,.4};
    vertices(buffer, quad, 4);
    glUseProgram(color);
    glClearColor(.25, .5, .75, .6);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glEnable(GL_BLEND);
    glBlendEquation(GL_FUNC_ADD);
    glBlendColor(.2, .4, .7, .3);
    const GLenum factors[] = {
        GL_ZERO, GL_ONE, GL_SRC_COLOR, GL_ONE_MINUS_SRC_COLOR,
        GL_DST_COLOR, GL_ONE_MINUS_DST_COLOR, GL_SRC_ALPHA,
        GL_ONE_MINUS_SRC_ALPHA, GL_DST_ALPHA, GL_ONE_MINUS_DST_ALPHA,
        GL_CONSTANT_COLOR, GL_ONE_MINUS_CONSTANT_COLOR,
        GL_CONSTANT_ALPHA, GL_ONE_MINUS_CONSTANT_ALPHA, GL_SRC_ALPHA_SATURATE,
    };
    char name[48];
    for (unsigned i = 0; i < sizeof(factors) / sizeof(factors[0]); ++i) {
        glBlendFuncSeparate(factors[i], GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA);
        glClear(GL_COLOR_BUFFER_BIT);
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
        snprintf(name, sizeof(name), "src_factor_%u", i);
        sample(name);
        /* SRC_ALPHA_SATURATE is a source-only factor in GLES2. */
        if (factors[i] == GL_SRC_ALPHA_SATURATE) continue;
        glBlendFuncSeparate(GL_SRC_ALPHA, factors[i], GL_ONE, factors[i]);
        glClear(GL_COLOR_BUFFER_BIT);
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
        snprintf(name, sizeof(name), "dst_factor_%u", i);
        sample(name);
    }
    const GLenum equations[] = {GL_FUNC_ADD, GL_FUNC_SUBTRACT, GL_FUNC_REVERSE_SUBTRACT};
    glBlendFuncSeparate(GL_ONE, GL_ONE, GL_ONE, GL_ONE);
    for (int i = 0; i < 3; ++i) {
        glBlendEquationSeparate(equations[i], equations[2 - i]);
        glClear(GL_COLOR_BUFFER_BIT);
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
        snprintf(name, sizeof(name), "equation_%d", i);
        sample(name);
    }
    glBlendEquation(GL_FUNC_ADD);
    glDisable(GL_BLEND);
    for (unsigned i = 0; i < 16; ++i) {
        glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
        glClear(GL_COLOR_BUFFER_BIT);
        glColorMask(i & 1, (i >> 1) & 1, (i >> 2) & 1, (i >> 3) & 1);
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
        snprintf(name, sizeof(name), "mask_%u", i);
        sample(name);
    }
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA);
    for (int i = 0; i < 3; ++i) {
        if (i == 1) glEnable(GL_BLEND); else glDisable(GL_BLEND);
        glClear(GL_COLOR_BUFFER_BIT);
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
        snprintf(name, sizeof(name), "enable_%d", i);
        sample(name);
    }
    glEnable(GL_BLEND);
    glBlendFuncSeparate(GL_CONSTANT_COLOR, GL_ONE_MINUS_CONSTANT_COLOR,
                        GL_CONSTANT_ALPHA, GL_ONE_MINUS_CONSTANT_ALPHA);
    /* More unique colors than the 32-entry variant cache, followed by
     * revisits to evicted and recent keys; each variant must be correct. */
    for (int i = 0; i < 43; ++i) {
        int k = i < 40 ? i : (i == 40 ? 0 : i == 41 ? 19 : 39);
        glBlendColor(k / 40.f, .4, .7, (40 - k) / 40.f);
        glClear(GL_COLOR_BUFFER_BIT);
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
        snprintf(name, sizeof(name), "constant_%d", i);
        sample(name);
    }
    glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA);
    for (unsigned i = 0; i < 16; ++i) {
        glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
        glClear(GL_COLOR_BUFFER_BIT);
        glColorMask(i & 1, (i >> 1) & 1, (i >> 2) & 1, (i >> 3) & 1);
        glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
        snprintf(name, sizeof(name), "blend_mask_%u", i);
        sample(name);
    }
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    GLint original_fbo;
    glGetIntegerv(GL_FRAMEBUFFER_BINDING, &original_fbo);
    GLuint rgb, rgb_fbo;
    glGenTextures(1, &rgb);
    glBindTexture(GL_TEXTURE_2D, rgb);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGB, 64, 64, 0, GL_RGB, GL_UNSIGNED_BYTE, NULL);
    glGenFramebuffers(1, &rgb_fbo);
    glBindFramebuffer(GL_FRAMEBUFFER, rgb_fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, rgb, 0);
    if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
        fprintf(stderr, "FRAMEBUFFER_FAIL rgb\n");
        exit(1);
    }
    glClear(GL_COLOR_BUFFER_BIT);
    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
    sample("format_rgb");
    glBindFramebuffer(GL_FRAMEBUFFER, original_fbo);
    glClear(GL_COLOR_BUFFER_BIT);
    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
    sample("format_rgba_restored");
    glDeleteFramebuffers(1, &rgb_fbo);
    glDeleteTextures(1, &rgb);
}

int main(int argc, char **argv)
{
    if (argc > 2 || (argc == 2 && strcmp(argv[1], "--state"))) {
        fprintf(stderr, "Usage: gpu-blend-check [--state]\n");
        return 1;
    }
    setbuf(stdout, NULL);
    setenv("EGL_PLATFORM", "surfaceless", 0);
    EGLDisplay display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
    if (!eglInitialize(display, NULL, NULL) || !eglBindAPI(EGL_OPENGL_ES_API)) return 1;
    EGLint ca[] = {EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
                   EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RED_SIZE,8,
                   EGL_GREEN_SIZE,8, EGL_BLUE_SIZE,8, EGL_ALPHA_SIZE,8,EGL_NONE};
    EGLConfig config;
    EGLint count;
    if (!eglChooseConfig(display, ca, &config, 1, &count) || count != 1) return 1;
    EGLint cx[] = {EGL_CONTEXT_CLIENT_VERSION,2,EGL_NONE};
    EGLint pb[] = {EGL_WIDTH,16,EGL_HEIGHT,16,EGL_NONE};
    EGLContext context = eglCreateContext(display, config, EGL_NO_CONTEXT, cx);
    EGLSurface surface = eglCreatePbufferSurface(display, config, pb);
    if (!eglMakeCurrent(display, surface, surface, context)) return 1;
    printf("# renderer: %s\n", glGetString(GL_RENDERER));
    GLuint output, fbo, buffer;
    glGenTextures(1, &output);
    glBindTexture(GL_TEXTURE_2D, output);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 64, 64, 0, GL_RGBA, GL_UNSIGNED_BYTE, NULL);
    glGenFramebuffers(1, &fbo);
    glBindFramebuffer(GL_FRAMEBUFFER, fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, output, 0);
    if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) return 1;
    glViewport(0, 0, 64, 64);
    glGenBuffers(1, &buffer);
    GLuint color = program("precision mediump float; varying vec4 c; void main(){gl_FragColor=c;}");
    GLuint textured = program("precision mediump float; varying vec4 c; uniform sampler2D t;"
                              "void main(){gl_FragColor=texture2D(t,c.xy);}");
    glUseProgram(color);
    glEnable(GL_BLEND);
    glBlendFuncSeparate(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA);
    GLfloat data[18 * 6];
    triangle(data, 1, 0, 0, .5);
    triangle(data + 18, 0, 1, 0, .5);
    vertices(buffer, data, 6);
    glClearColor(0, 0, 1, 1);
    glClear(GL_COLOR_BUFFER_BIT);
    glDrawArrays(GL_TRIANGLES, 0, 6);
    sample("overlap_batch");
    glClear(GL_COLOR_BUFFER_BIT);
    glDrawArrays(GL_TRIANGLES, 0, 3);
    glDrawArrays(GL_TRIANGLES, 3, 3);
    sample("overlap_draws");
    for (int i = 0; i < 6; ++i)
        triangle(data + 18 * i, i % 2, (i + 1) % 2, .25, .25);
    vertices(buffer, data, 18);
    glClear(GL_COLOR_BUFFER_BIT);
    glDrawArrays(GL_TRIANGLES, 0, 18);
    sample("overlap_six");
    const float alphas[5] = {0, .25, .5, .75, 1};
    for (int i = 0; i < 5; ++i) {
        triangle(data, .8, .4, .2, alphas[i]);
        vertices(buffer, data, 3);
        glClearColor(.1, .2, .3, .25);
        glClear(GL_COLOR_BUFFER_BIT);
        glDrawArrays(GL_TRIANGLES, 0, 3);
        char name[32];
        snprintf(name, sizeof(name), "alpha_%d", i);
        sample(name);
    }
    const GLfloat quad[] = {-1,-1, 1,0,0,.5, 1,-1, 1,0,0,.5,
                           -1,1, 1,0,0,.5, 1,1, 1,0,0,.5};
    vertices(buffer, quad, 4);
    glClearColor(0, 0, 1, 1);
    glClear(GL_COLOR_BUFFER_BIT);
    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
    sample("quad_seam");
    triangle(data, 1, 0, 0, .2);
    data[9] = 1; data[8] = 0; data[11] = .5;
    data[16] = 1; data[14] = 0; data[17] = .8;
    vertices(buffer, data, 3);
    glClear(GL_COLOR_BUFFER_BIT);
    glDrawArrays(GL_TRIANGLES, 0, 3);
    sample("gradient_alpha");
    GLuint source;
    glGenTextures(1, &source);
    glBindTexture(GL_TEXTURE_2D, source);
    const unsigned char pixels[] = {255,0,0,64, 0,255,0,128, 0,0,255,192, 255,255,255,255};
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 2, 2, 0, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    const GLfloat uv[] = {-1,-1, 0,0,0,0, 1,-1, 1,0,0,0,
                         -1,1, 0,1,0,0, 1,1, 1,1,0,0};
    vertices(buffer, uv, 4);
    glUseProgram(textured);
    glUniform1i(glGetUniformLocation(textured, "t"), 0);
    glClearColor(.2, .3, .4, .25);
    glClear(GL_COLOR_BUFFER_BIT);
    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
    sample("texture_alpha");
    if (argc == 2) state_cases(color, buffer);
    glFinish();
    glDeleteProgram(color); glDeleteProgram(textured);
    glDeleteBuffers(1, &buffer); glDeleteFramebuffers(1, &fbo);
    glDeleteTextures(1, &source); glDeleteTextures(1, &output);
    eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
    eglDestroyContext(display, context); eglDestroySurface(display, surface); eglTerminate(display);
    return 0;
}
