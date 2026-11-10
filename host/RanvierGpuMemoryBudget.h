#pragma once
#include <atomic>
#include <cstddef>
#include <algorithm>

// Bounds accounted texture storage across hosts and retained generations, not driver-private overhead.
class RvGpuMemoryBudget {
public:
    static constexpr size_t limit = 256 * 1024 * 1024;
    static constexpr size_t minimumAllocation = 64 * 1024;
    static bool canFit(int width, int height, size_t bytesPerPixel)
    {
        return width > 0 && height > 0 && bytesPerPixel
            && static_cast<size_t>(width) <= limit / bytesPerPixel / height;
    }
    static size_t acquire(int width, int height, size_t bytesPerPixel)
    {
        if (!canFit(width, height, bytesPerPixel))
            return 0;
        size_t bytes = std::max(minimumAllocation, static_cast<size_t>(width) * height * bytesPerPixel);
        auto current = used.load();
        do {
            if (current > limit - bytes)
                return 0;
        } while (!used.compare_exchange_weak(current, current + bytes));
        return bytes;
    }
    static void release(size_t bytes) { used.fetch_sub(bytes); }
private:
    static inline std::atomic<size_t> used { 0 };
};
