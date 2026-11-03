#import <AppKit/AppKit.h>
#import <objc/runtime.h>
#include <atomic>

static std::atomic<bool> forcedReducedMotion { false };
static Method reducedMotionMethod;
static IMP originalReducedMotion;

static BOOL reducedMotionForTest(id, SEL)
{
    return forcedReducedMotion.load();
}

extern "C" int project2_cocoa_motion_set(int reduced)
{
    @autoreleasepool {
        if (!originalReducedMotion) {
            reducedMotionMethod = class_getInstanceMethod([NSWorkspace class], @selector(accessibilityDisplayShouldReduceMotion));
            if (!reducedMotionMethod)
                return -1;
            originalReducedMotion = method_setImplementation(reducedMotionMethod, reinterpret_cast<IMP>(reducedMotionForTest));
        }
        forcedReducedMotion.store(!!reduced);
        return [[NSWorkspace sharedWorkspace] accessibilityDisplayShouldReduceMotion] == !!reduced ? 0 : -2;
    }
}

extern "C" void project2_cocoa_motion_restore()
{
    if (originalReducedMotion) {
        method_setImplementation(reducedMotionMethod, originalReducedMotion);
        originalReducedMotion = nullptr;
    }
}
