#pragma once
#include <memory>

enum class RvGpuReadiness { Ready, NotReady, Failed };

// Internal transport. The caller makes the process compositor context current before creation/rendering.
class RvD3D11Surface {
public:
    static std::shared_ptr<RvD3D11Surface> create(void* consumerDevice, int width, int height, bool (*makeCurrent)(), bool bounded = false);
    ~RvD3D11Surface();
    bool matches(void* consumerDevice, int width, int height) const;
    bool available() const;
    bool beginProducer();
    bool finishProducer();
    void cancelProducer();
    bool releaseConsumer(bool retiring = false);
    RvGpuReadiness tryBeginProducer();
    bool submitProducer();
    RvGpuReadiness tryAcquireConsumer();
    RvGpuReadiness tryRetire();
    unsigned framebuffer() const;
    void* texture() const;
    int width() const;
    int height() const;
private:
    struct State;
    explicit RvD3D11Surface(std::unique_ptr<State>);
    std::unique_ptr<State> state;
};
