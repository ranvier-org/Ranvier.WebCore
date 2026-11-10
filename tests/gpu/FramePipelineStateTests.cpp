#include "../../host/RanvierFramePipeline.h"
#include "../../host/RanvierGpuMemoryBudget.h"
#include <cassert>

int main()
{
    auto reserved = RvGpuMemoryBudget::acquire(8192, 4096, 8);
    assert(reserved == RvGpuMemoryBudget::limit);
    assert(!RvGpuMemoryBudget::acquire(1, 1, 4));
    RvGpuMemoryBudget::release(reserved);
    assert(!RvGpuMemoryBudget::acquire(2147483647, 2147483647, 8));
    reserved = RvGpuMemoryBudget::acquire(1, 1, 4);
    assert(reserved == RvGpuMemoryBudget::minimumAllocation);
    RvGpuMemoryBudget::release(reserved);
    RvFramePipeline state;
    auto a = state.reserve(1);
    auto b = state.reserve(2);
    auto c = state.reserve(3);
    assert(a == 0 && b == 1 && c == 2);
    assert(state.reserve(4) == -1);
    assert(state.newestReady() == -1);
    state.complete(b);
    assert(state.newestReady() == b);
    state.lease(b);
    state.complete(a);
    assert(state.newestReady() == -1); // Late completion cannot replace a newer leased image.
    state.retire(a);
    assert(state.reserve(4) == -1); // Retirement still owns GPU storage.
    state.recycle(a);
    assert(state.reserve(4) == a);
    state.complete(a);
    assert(state.newestReady() == a);
    state.lease(a);
    state.retire(b);
    state.recycle(b);
    assert(state.reserve(5) == b);
    state.retire(c); // Device loss or cancelled producer.
    state.recycle(c);
    assert(state.reserve(5) == -1); // Submission identity is monotonic.
    assert(state.reserve(6) == c);
    state.complete(c);
    state.lease(c);
    state.retire(c);
    state.recycle(c);
    // Resizing uses the same three slots, including leased generations.
    assert(state.reserve(7) == c);
}
