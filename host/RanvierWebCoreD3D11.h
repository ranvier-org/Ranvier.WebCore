#pragma once
#include <memory>

// Internal transport. The caller makes the process compositor context current before creation/rendering.
class RvD3D11Surface {
public:
    static std::shared_ptr<RvD3D11Surface> create(void* consumerDevice, int width, int height, bool (*makeCurrent)());
    ~RvD3D11Surface();
    bool matches(void* consumerDevice, int width, int height) const;
    bool available() const;
    bool beginProducer();
    bool finishProducer();
    void cancelProducer();
    bool releaseConsumer();
    unsigned framebuffer() const;
    void* texture() const;
    int width() const;
    int height() const;
private:
    struct State;
    explicit RvD3D11Surface(std::unique_ptr<State>);
    std::unique_ptr<State> state;
};
