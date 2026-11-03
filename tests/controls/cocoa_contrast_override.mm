#import <AppKit/AppKit.h>
#import <objc/runtime.h>
#include <atomic>

static std::atomic<bool> forcedContrast { false };
static std::atomic<unsigned> calls { 0 };
static Method contrastMethod;
static IMP originalContrast;

static BOOL contrastForTest(id, SEL)
{
    ++calls;
    return forcedContrast.load();
}

extern "C" int project2_cocoa_contrast_set(int increased)
{
    @autoreleasepool {
        if (![NSThread isMainThread])
            return -2;
        if (!originalContrast) {
            contrastMethod = class_getInstanceMethod([NSWorkspace class], @selector(accessibilityDisplayShouldIncreaseContrast));
            if (!contrastMethod)
                return -1;
            originalContrast = method_setImplementation(contrastMethod, reinterpret_cast<IMP>(contrastForTest));
        }
        forcedContrast.store(!!increased);
        calls.store(0);
        return 0;
    }
}

extern "C" unsigned project2_cocoa_contrast_calls()
{
    return calls.load();
}

extern "C" int project2_cocoa_contrast_restore()
{
    if (![NSThread isMainThread])
        return -2;
    if (originalContrast) {
        method_setImplementation(contrastMethod, originalContrast);
        originalContrast = nullptr;
    }
    return 0;
}
