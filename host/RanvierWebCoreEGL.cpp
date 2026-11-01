#include "config.h"
#include "RanvierWebCoreEGL.h"

#if defined(__linux__) && RANVIER_COMPOSITING
#include <epoxy/egl.h>
#include <epoxy/gl.h>
#include <WebCore/GLContext.h>
#include <utility>

RvEGLContextScope::RvEGLContextScope()
    : display(eglGetCurrentDisplay()), context(eglGetCurrentContext())
    , draw(eglGetCurrentSurface(EGL_DRAW)), read(eglGetCurrentSurface(EGL_READ))
{
    // SDL switches contexts outside GLContextWrapper's current-context cache.
    if (auto* current = WebCore::GLContext::current())
        current->unmakeContextCurrent();
}

RvEGLContextScope::~RvEGLContextScope()
{
    if (auto* current = WebCore::GLContext::current())
        current->unmakeContextCurrent();
    if (display != EGL_NO_DISPLAY)
        eglMakeCurrent(display, draw, read, context);
    else if (auto currentDisplay = eglGetCurrentDisplay(); currentDisplay != EGL_NO_DISPLAY)
        eglMakeCurrent(currentDisplay, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT);
}

struct RvEGLSurface::State {
    EGLDisplay display { EGL_NO_DISPLAY };
    EGLImageKHR image { EGL_NO_IMAGE_KHR };
    GLuint texture { 0 };
    GLuint framebuffer { 0 };
    GLuint depthStencil { 0 };
    int width { 0 };
    int height { 0 };
    bool acquired { false };
    EGLContext consumerContext { EGL_NO_CONTEXT };
    bool (*makeCurrent)() { nullptr };

    ~State()
    {
        RvEGLContextScope scope;
        if (!makeCurrent || !makeCurrent())
            return;
        if (image != EGL_NO_IMAGE_KHR)
            eglDestroyImageKHR(display, image);
        glDeleteFramebuffers(1, &framebuffer);
        glDeleteRenderbuffers(1, &depthStencil);
        glDeleteTextures(1, &texture);
    }
};

RvEGLSurface::RvEGLSurface(std::unique_ptr<State> state)
    : state(std::move(state)) { }
RvEGLSurface::~RvEGLSurface() = default;

std::shared_ptr<RvEGLSurface> RvEGLSurface::create(int width, int height, bool (*makeCurrent)())
{
    RvEGLContextScope scope;
    auto state = std::make_unique<State>();
    state->makeCurrent = makeCurrent;
    if (!makeCurrent || !makeCurrent() || width <= 0 || height <= 0)
        return nullptr;
    state->display = eglGetCurrentDisplay();
    state->width = width;
    state->height = height;
    if (!epoxy_has_egl_extension(state->display, "EGL_KHR_image_base")
        || !epoxy_has_egl_extension(state->display, "EGL_KHR_gl_texture_2D_image"))
        return nullptr;
    glGenTextures(1, &state->texture);
    glBindTexture(GL_TEXTURE_2D, state->texture);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0, GL_RGBA, GL_UNSIGNED_BYTE, nullptr);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glGenRenderbuffers(1, &state->depthStencil);
    glBindRenderbuffer(GL_RENDERBUFFER, state->depthStencil);
    glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH24_STENCIL8, width, height);
    glGenFramebuffers(1, &state->framebuffer);
    glBindFramebuffer(GL_FRAMEBUFFER, state->framebuffer);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, state->texture, 0);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, state->depthStencil);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_STENCIL_ATTACHMENT, GL_RENDERBUFFER, state->depthStencil);
    if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE)
        return nullptr;
    const EGLint attributes[] = { EGL_GL_TEXTURE_LEVEL_KHR, 0, EGL_IMAGE_PRESERVED_KHR, EGL_TRUE, EGL_NONE };
    state->image = eglCreateImageKHR(state->display, eglGetCurrentContext(), EGL_GL_TEXTURE_2D_KHR,
        reinterpret_cast<EGLClientBuffer>(static_cast<uintptr_t>(state->texture)), attributes);
    if (state->image == EGL_NO_IMAGE_KHR || glGetError() != GL_NO_ERROR)
        return nullptr;
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    return std::shared_ptr<RvEGLSurface>(new RvEGLSurface(std::move(state)));
}

bool RvEGLSurface::matches(int width, int height) const { return state->width == width && state->height == height; }
bool RvEGLSurface::available() const { return !state->acquired; }
bool RvEGLSurface::beginProducer() { return !state->acquired && state->makeCurrent(); }
bool RvEGLSurface::finishProducer(void* consumerContext)
{
    glFinish();
    if (glGetError() != GL_NO_ERROR)
        return false;
    state->acquired = true;
    state->consumerContext = consumerContext;
    return true;
}
void RvEGLSurface::cancelProducer() { glBindFramebuffer(GL_FRAMEBUFFER, 0); }
bool RvEGLSurface::releaseConsumer()
{
    if (!state->acquired || eglGetCurrentDisplay() != state->display || eglGetCurrentContext() != state->consumerContext)
        return false;
    glFinish();
    if (glGetError() != GL_NO_ERROR)
        return false;
    state->acquired = false;
    return true;
}
unsigned RvEGLSurface::framebuffer() const { return state->framebuffer; }
void* RvEGLSurface::image() const { return state->image; }
int RvEGLSurface::width() const { return state->width; }
int RvEGLSurface::height() const { return state->height; }
#endif
