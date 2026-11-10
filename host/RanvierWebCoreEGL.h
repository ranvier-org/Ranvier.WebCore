#pragma once
#include <memory>

namespace WebCore { class GLContext; }

class RvEGLContextScope {
public:
    RvEGLContextScope();
    ~RvEGLContextScope();
    void restore();
private:
    void* display;
    void* context;
    void* draw;
    void* read;
    WebCore::GLContext* nativeContext { nullptr };
};

class RvEGLSurface {
public:
    static std::shared_ptr<RvEGLSurface> create(int width, int height, bool (*makeCurrent)(), bool bounded = false, bool* exhausted = nullptr);
    static bool supportsPipeline(void* display);
    ~RvEGLSurface();
    bool matches(int width, int height) const;
    bool available() const;
    bool beginProducer();
    bool finishProducer(void* consumerContext);
    void cancelProducer();
    bool releaseConsumer(bool nonblocking = false);
    bool submitProducer(void* consumerContext);
    int producerReady();
    int retirementReady();
    void discardReady();
    unsigned framebuffer() const;
    void* image() const;
    int width() const;
    int height() const;
private:
    struct State;
    explicit RvEGLSurface(std::unique_ptr<State>);
    std::unique_ptr<State> state;
};
