#pragma once
#include <memory>

class RvEGLContextScope {
public:
    RvEGLContextScope();
    ~RvEGLContextScope();
private:
    void* display;
    void* context;
    void* draw;
    void* read;
};

class RvEGLSurface {
public:
    static std::shared_ptr<RvEGLSurface> create(int width, int height, bool (*makeCurrent)());
    ~RvEGLSurface();
    bool matches(int width, int height) const;
    bool available() const;
    bool beginProducer();
    bool finishProducer(void* consumerContext);
    void cancelProducer();
    bool releaseConsumer();
    unsigned framebuffer() const;
    void* image() const;
    int width() const;
    int height() const;
private:
    struct State;
    explicit RvEGLSurface(std::unique_ptr<State>);
    std::unique_ptr<State> state;
};
