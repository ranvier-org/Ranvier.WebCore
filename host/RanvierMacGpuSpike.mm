#include "config.h"
#include "RanvierMacGpuSpike.h"

#if defined(RANVIER_MAC_GPU_SPIKE) && RANVIER_MAC_GPU_SPIKE

#import <Foundation/Foundation.h>
#import <IOSurface/IOSurface.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <EGL/eglext_angle.h>
#include <GLES2/gl2.h>
#include <GLES2/gl2ext.h>
#include <cstring>
#include <limits>
#include <string>

namespace {
EGLDisplay display { EGL_NO_DISPLAY };
std::string identity;

bool extension(const char* extensions, const char* name)
{
    if (!extensions)
        return false;
    size_t length = std::strlen(name);
    for (auto* p = extensions; (p = std::strstr(p, name)); p += length) {
        if ((p == extensions || p[-1] == ' ') && (!p[length] || p[length] == ' '))
            return true;
    }
    return false;
}
}

void* rvMacSpikeDisplay()
{
    if (display != EGL_NO_DISPLAY)
        return display;
    auto getPlatform = reinterpret_cast<PFNEGLGETPLATFORMDISPLAYEXTPROC>(eglGetProcAddress("eglGetPlatformDisplayEXT"));
    if (!getPlatform)
        return nullptr;
    EGLint attributes[] { EGL_PLATFORM_ANGLE_TYPE_ANGLE, EGL_PLATFORM_ANGLE_TYPE_METAL_ANGLE, EGL_NONE };
    auto candidate = getPlatform(EGL_PLATFORM_ANGLE_ANGLE, nullptr, attributes);
    if (candidate == EGL_NO_DISPLAY || !eglInitialize(candidate, nullptr, nullptr))
        return nullptr;
    if (!extension(eglQueryString(candidate, EGL_EXTENSIONS), "EGL_ANGLE_iosurface_client_buffer")) {
        eglTerminate(candidate);
        return nullptr;
    }
    display = candidate;
    return display;
}

struct RvMacSpikeSurface::State {
    IOSurfaceRef ioSurface { nullptr };
    EGLSurface eglSurface { EGL_NO_SURFACE };
    GLuint texture { 0 };
    GLuint target { 0 };
    GLuint depthStencil { 0 };
    int width { 0 };
    int height { 0 };
    bool bound { false };
    bool (*makeCurrent)() { nullptr };

    ~State()
    {
        if (makeCurrent && makeCurrent()) {
            if (bound)
                eglReleaseTexImage(display, eglSurface, EGL_BACK_BUFFER);
            glDeleteFramebuffers(1, &target);
            glDeleteRenderbuffers(1, &depthStencil);
            glDeleteTextures(1, &texture);
        }
        if (eglSurface != EGL_NO_SURFACE)
            eglDestroySurface(display, eglSurface);
        if (ioSurface)
            CFRelease(ioSurface);
    }
};

RvMacSpikeSurface::RvMacSpikeSurface(std::unique_ptr<State> value)
    : state(std::move(value)) { }
RvMacSpikeSurface::~RvMacSpikeSurface() = default;

std::unique_ptr<RvMacSpikeSurface> RvMacSpikeSurface::create(int width, int height, bool (*makeCurrent)())
{
    if (width <= 0 || height <= 0 || width > std::numeric_limits<int>::max() / 4
        || !makeCurrent || !makeCurrent() || !rvMacSpikeDisplay())
        return nullptr;
    const char* renderer = reinterpret_cast<const char*>(glGetString(GL_RENDERER));
    if (!renderer || !std::strstr(renderer, "Metal"))
        return nullptr;
    if (identity.empty()) {
        identity = std::string(eglQueryString(display, EGL_VENDOR)) + "; "
            + eglQueryString(display, EGL_VERSION) + "; " + renderer + "; GL="
            + reinterpret_cast<const char*>(glGetString(GL_VERSION)) + "; EGL extensions="
            + eglQueryString(display, EGL_EXTENSIONS);
    }
    auto value = std::make_unique<State>();
    value->width = width;
    value->height = height;
    value->makeCurrent = makeCurrent;
    @autoreleasepool {
        NSDictionary* properties = @{
            (__bridge id)kIOSurfaceWidth: @(width), (__bridge id)kIOSurfaceHeight: @(height),
            (__bridge id)kIOSurfaceBytesPerElement: @4, (__bridge id)kIOSurfaceBytesPerRow: @(static_cast<size_t>(width) * 4),
            (__bridge id)kIOSurfacePixelFormat: @0x42475241
        };
        value->ioSurface = IOSurfaceCreate((__bridge CFDictionaryRef)properties);
    }
    if (!value->ioSurface)
        return nullptr;
    EGLConfig config = nullptr;
    EGLint count = 0;
    EGLint configAttributes[] { EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
        EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_NONE };
    if (!eglChooseConfig(display, configAttributes, &config, 1, &count) || count != 1)
        return nullptr;
    EGLint target = 0;
    if (!eglGetConfigAttrib(display, config, EGL_BIND_TO_TEXTURE_TARGET_ANGLE, &target) || target != EGL_TEXTURE_2D)
        return nullptr;
    EGLint attributes[] { EGL_WIDTH, width, EGL_HEIGHT, height, EGL_TEXTURE_FORMAT, EGL_TEXTURE_RGBA,
        EGL_TEXTURE_TARGET, target, EGL_IOSURFACE_PLANE_ANGLE, 0,
        EGL_TEXTURE_TYPE_ANGLE, GL_UNSIGNED_BYTE, EGL_TEXTURE_INTERNAL_FORMAT_ANGLE, GL_BGRA_EXT, EGL_NONE };
    value->eglSurface = eglCreatePbufferFromClientBuffer(display, EGL_IOSURFACE_ANGLE,
        reinterpret_cast<EGLClientBuffer>(value->ioSurface), config, attributes);
    if (value->eglSurface == EGL_NO_SURFACE)
        return nullptr;
    glGenTextures(1, &value->texture);
    glBindTexture(GL_TEXTURE_2D, value->texture);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    value->bound = eglBindTexImage(display, value->eglSurface, EGL_BACK_BUFFER);
    if (!value->bound)
        return nullptr;
    glGenRenderbuffers(1, &value->depthStencil);
    glBindRenderbuffer(GL_RENDERBUFFER, value->depthStencil);
    glRenderbufferStorage(GL_RENDERBUFFER, GL_DEPTH24_STENCIL8_OES, width, height);
    glGenFramebuffers(1, &value->target);
    glBindFramebuffer(GL_FRAMEBUFFER, value->target);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, value->texture, 0);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER, value->depthStencil);
    glFramebufferRenderbuffer(GL_FRAMEBUFFER, GL_STENCIL_ATTACHMENT, GL_RENDERBUFFER, value->depthStencil);
    bool complete = glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE && glGetError() == GL_NO_ERROR;
    glBindFramebuffer(GL_FRAMEBUFFER, 0);
    return complete ? std::unique_ptr<RvMacSpikeSurface>(new RvMacSpikeSurface(std::move(value))) : nullptr;
}

unsigned RvMacSpikeSurface::framebuffer() const { return state->target; }
void* RvMacSpikeSurface::surface() const { return state->ioSurface; }
int RvMacSpikeSurface::width() const { return state->width; }
int RvMacSpikeSurface::height() const { return state->height; }

bool RvMacSpikeSurface::finishProducer()
{
    glFinish();
    if (glGetError() != GL_NO_ERROR)
        return false;
    bool released = eglReleaseTexImage(display, state->eglSurface, EGL_BACK_BUFFER);
    state->bound = !released;
    return released;
}

const char* rvMacSpikeIdentity()
{
    return identity.empty() ? nullptr : identity.c_str();
}

struct RvMacSpikeInputSurface::State {
    IOSurfaceRef ioSurface { nullptr };
    EGLSurface eglSurface { EGL_NO_SURFACE };
    GLuint texture { 0 };
    bool bound { false };
    bool failed { false };
    bool (*makeCurrent)() { nullptr };

    ~State()
    {
        if (makeCurrent && makeCurrent()) {
            if (bound) {
                glFinish();
                eglReleaseTexImage(display, eglSurface, EGL_BACK_BUFFER);
            }
            glDeleteTextures(1, &texture);
        }
        if (eglSurface != EGL_NO_SURFACE)
            eglDestroySurface(display, eglSurface);
        if (ioSurface)
            CFRelease(ioSurface);
    }
};

RvMacSpikeInputSurface::RvMacSpikeInputSurface(std::unique_ptr<State> value)
    : state(std::move(value)) { }
RvMacSpikeInputSurface::~RvMacSpikeInputSurface() = default;

std::unique_ptr<RvMacSpikeInputSurface> RvMacSpikeInputSurface::create(void* pointer, bool (*makeCurrent)())
{
    auto ioSurface = static_cast<IOSurfaceRef>(pointer);
    if (!ioSurface || !makeCurrent || !makeCurrent() || !rvMacSpikeDisplay())
        return nullptr;
    auto width = IOSurfaceGetWidth(ioSurface);
    auto height = IOSurfaceGetHeight(ioSurface);
    auto rowBytes = IOSurfaceGetBytesPerRow(ioSurface);
    if (!width || !height || width > static_cast<size_t>(std::numeric_limits<int>::max() / 4)
        || height > static_cast<size_t>(std::numeric_limits<int>::max())
        || IOSurfaceGetPlaneCount(ioSurface) != 0 || IOSurfaceGetPixelFormat(ioSurface) != 0x42475241
        || IOSurfaceGetBytesPerElement(ioSurface) != 4 || rowBytes < width * 4
        || rowBytes > std::numeric_limits<size_t>::max() / height || IOSurfaceGetAllocSize(ioSurface) < rowBytes * height)
        return nullptr;
    GLint maximum = 0;
    glGetIntegerv(GL_MAX_TEXTURE_SIZE, &maximum);
    if (maximum <= 0 || width > static_cast<size_t>(maximum) || height > static_cast<size_t>(maximum)
        || glGetError() != GL_NO_ERROR)
        return nullptr;
    auto value = std::make_unique<State>();
    value->ioSurface = ioSurface;
    CFRetain(ioSurface);
    value->makeCurrent = makeCurrent;
    EGLConfig config = nullptr;
    EGLint count = 0, target = 0;
    EGLint configAttributes[] { EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
        EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8, EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_NONE };
    if (!eglChooseConfig(display, configAttributes, &config, 1, &count) || count != 1
        || !eglGetConfigAttrib(display, config, EGL_BIND_TO_TEXTURE_TARGET_ANGLE, &target) || target != EGL_TEXTURE_2D)
        return nullptr;
    EGLint attributes[] { EGL_WIDTH, static_cast<EGLint>(width), EGL_HEIGHT, static_cast<EGLint>(height),
        EGL_TEXTURE_FORMAT, EGL_TEXTURE_RGBA, EGL_TEXTURE_TARGET, target, EGL_IOSURFACE_PLANE_ANGLE, 0,
        EGL_TEXTURE_TYPE_ANGLE, GL_UNSIGNED_BYTE, EGL_TEXTURE_INTERNAL_FORMAT_ANGLE, GL_BGRA_EXT,
        EGL_IOSURFACE_USAGE_HINT_ANGLE, EGL_IOSURFACE_READ_HINT_ANGLE, EGL_NONE };
    value->eglSurface = eglCreatePbufferFromClientBuffer(display, EGL_IOSURFACE_ANGLE,
        reinterpret_cast<EGLClientBuffer>(ioSurface), config, attributes);
    if (value->eglSurface == EGL_NO_SURFACE)
        return nullptr;
    glGenTextures(1, &value->texture);
    glBindTexture(GL_TEXTURE_2D, value->texture);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
    glBindTexture(GL_TEXTURE_2D, 0);
    if (!value->texture || glGetError() != GL_NO_ERROR)
        return nullptr;
    return std::unique_ptr<RvMacSpikeInputSurface>(new RvMacSpikeInputSurface(std::move(value)));
}

bool RvMacSpikeInputSurface::begin()
{
    if (state->failed || state->bound || !state->makeCurrent() || eglGetCurrentDisplay() != display)
        return false;
    glBindTexture(GL_TEXTURE_2D, state->texture);
    state->bound = eglBindTexImage(display, state->eglSurface, EGL_BACK_BUFFER);
    glBindTexture(GL_TEXTURE_2D, 0);
    state->failed = !state->bound || glGetError() != GL_NO_ERROR;
    if (state->failed && state->bound)
        end();
    return !state->failed;
}

bool RvMacSpikeInputSurface::end()
{
    if (!state->bound)
        return !state->failed;
    if (!state->makeCurrent()) {
        state->failed = true;
        return false;
    }
    glFinish();
    bool completed = glGetError() == GL_NO_ERROR;
    bool released = eglReleaseTexImage(display, state->eglSurface, EGL_BACK_BUFFER);
    state->bound = !released;
    state->failed |= !completed || !released;
    return !state->failed;
}

unsigned RvMacSpikeInputSurface::texture() const { return state->texture; }
#endif
