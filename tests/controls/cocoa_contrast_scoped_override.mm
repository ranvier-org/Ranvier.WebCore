#import <AppKit/AppKit.h>
#import <objc/runtime.h>
#include <atomic>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>

static std::atomic<bool> forcedContrast { false };
static std::atomic<bool> installed { false };
static std::atomic<unsigned> themeCalls { 0 };
static std::atomic<unsigned> platformCalls { 0 };
static std::atomic<IMP> originalContrast { nullptr };
static Method contrastMethod;

static bool isThemePreferenceCaller(void* address)
{
    Dl_info info { };
    if (!dladdr(address, &info) || !info.dli_sname || !info.dli_fname)
        return false;
    const char* file = std::strrchr(info.dli_fname, '/');
    file = file ? file + 1 : info.dli_fname;
    return !std::strcmp(file, "libWebCore.dylib")
        && (!std::strcmp(info.dli_sname, "_ZNK7WebCore8ThemeMac21userPreferredContrastEv")
            || !std::strcmp(info.dli_sname, "__ZNK7WebCore8ThemeMac21userPreferredContrastEv"));
}

static BOOL contrastForTest(id object, SEL selector)
{
    void* caller = __builtin_extract_return_addr(__builtin_return_address(0));
    if (installed.load(std::memory_order_acquire) && isThemePreferenceCaller(caller)) {
        ++themeCalls;
        return forcedContrast.load();
    }
    ++platformCalls;
    IMP original = originalContrast.load(std::memory_order_acquire);
    if (!original)
        std::abort();
    return reinterpret_cast<BOOL (*)(id, SEL)>(original)(object, selector);
}

extern "C" int project2_cocoa_contrast_set(int increased)
{
    @autoreleasepool {
        if (![NSThread isMainThread])
            return -2;
        forcedContrast.store(!!increased);
        themeCalls.store(0);
        platformCalls.store(0);
        if (!installed.load()) {
            contrastMethod = class_getInstanceMethod([NSWorkspace class], @selector(accessibilityDisplayShouldIncreaseContrast));
            if (!contrastMethod)
                return -1;
            originalContrast.store(method_getImplementation(contrastMethod), std::memory_order_release);
            installed.store(true, std::memory_order_release);
            method_setImplementation(contrastMethod, reinterpret_cast<IMP>(contrastForTest));
        }
        return 0;
    }
}

extern "C" unsigned project2_cocoa_contrast_calls()
{
    return themeCalls.load();
}

extern "C" unsigned project2_cocoa_contrast_platform_calls()
{
    return platformCalls.load();
}

extern "C" int project2_cocoa_contrast_platform_value()
{
    @autoreleasepool {
        if (![NSThread isMainThread])
            return -2;
        return [[NSWorkspace sharedWorkspace] accessibilityDisplayShouldIncreaseContrast];
    }
}

extern "C" int project2_cocoa_contrast_reset_calls()
{
    if (![NSThread isMainThread])
        return -2;
    themeCalls.store(0);
    platformCalls.store(0);
    return 0;
}

extern "C" int project2_cocoa_contrast_restore()
{
    if (![NSThread isMainThread])
        return -2;
    if (installed.exchange(false, std::memory_order_acq_rel))
        method_setImplementation(contrastMethod, originalContrast.load(std::memory_order_acquire));
    return 0;
}
