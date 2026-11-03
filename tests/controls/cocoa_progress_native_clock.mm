#import <AppKit/AppKit.h>
#import <CoreGraphics/CoreGraphics.h>
#import <objc/runtime.h>
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <dlfcn.h>

@interface NSAppearance (Project2ProgressClock)
- (void)_drawInRect:(NSRect)rect context:(CGContextRef)context options:(NSDictionary *)options;
@end

static std::atomic<int32_t> requestedSystemMotion;
static std::atomic<int32_t> systemGetterCalls;

static BOOL controlledSystemMotion(id, SEL)
{
    ++systemGetterCalls;
    return requestedSystemMotion.load() ? YES : NO;
}

class ScopedSystemMotion {
public:
    explicit ScopedSystemMotion(Method method)
        : m_method(method)
        , m_previous(method_setImplementation(method, reinterpret_cast<IMP>(controlledSystemMotion)))
    {
    }

    ~ScopedSystemMotion() { method_setImplementation(m_method, m_previous); }

private:
    Method m_method;
    IMP m_previous;
};

static NSString* coreUIConstant(const char* name)
{
    auto* address = static_cast<CFStringRef*>(dlsym(RTLD_DEFAULT, name));
    if (!address || !*address)
        fprintf(stderr, "CoreUI constant unavailable: %s\n", name);
    return address ? (__bridge NSString*)*address : nil;
}

extern "C" uintptr_t project2_native_progress_getter_implementation()
{
    Method method = class_getInstanceMethod([NSWorkspace class], @selector(accessibilityDisplayShouldReduceMotion));
    return method ? reinterpret_cast<uintptr_t>(method_getImplementation(method)) : 0;
}

extern "C" int32_t project2_native_progress_clock(int32_t systemReduced, double startTime, double currentTime,
    double position, uint8_t* rgba, size_t capacity, int32_t* getterCalls)
{
    if (![NSThread isMainThread])
        return -1;
    if ((systemReduced != 0 && systemReduced != 1) || !std::isfinite(startTime) || !std::isfinite(currentTime)
        || !std::isfinite(position) || startTime < 0 || currentTime < startTime || position < -1 || position > 1
        || !rgba || capacity != 512 * 40 * 4 || !getterCalls)
        return -2;

    Method method = class_getInstanceMethod([NSWorkspace class], @selector(accessibilityDisplayShouldReduceMotion));
    if (!method)
        return -3;

    NSString* widgetKey = coreUIConstant("kCUIWidgetKey");
    NSString* widget = coreUIConstant(position < 0 ? "kCUIWidgetProgressIndeterminateBar" : "kCUIWidgetProgressBar");
    NSString* valueKey = coreUIConstant("kCUIValueKey");
    NSString* sizeKey = coreUIConstant("kCUISizeKey");
    NSString* size = coreUIConstant("kCUISizeSmall");
    NSString* directionKey = coreUIConstant("kCUIUserInterfaceLayoutDirectionKey");
    NSString* direction = coreUIConstant("kCUIUserInterfaceLayoutDirectionLeftToRight");
    NSString* scaleKey = coreUIConstant("kCUIScaleKey");
    NSString* stateKey = coreUIConstant("kCUIPresentationStateKey");
    NSString* state = coreUIConstant("kCUIPresentationStateActiveKey");
    NSString* orientationKey = coreUIConstant("kCUIOrientationKey");
    NSString* orientation = coreUIConstant("kCUIOrientHorizontal");
    NSString* startKey = coreUIConstant("kCUIAnimationStartTimeKey");
    NSString* timeKey = coreUIConstant("kCUIAnimationTimeKey");
    if (!widgetKey || !widget || !valueKey || !sizeKey || !size || !directionKey || !direction || !scaleKey
        || !stateKey || !state || !orientationKey || !orientation || !startKey || !timeKey)
        return -4;

    requestedSystemMotion.store(systemReduced);
    systemGetterCalls.store(0);
    ScopedSystemMotion controlled(method);

    @autoreleasepool {
        CGColorSpaceRef colorSpace = CGColorSpaceCreateDeviceRGB();
        if (!colorSpace)
            return -5;
        CGContextRef context = CGBitmapContextCreate(rgba, 512, 40, 8, 512 * 4, colorSpace,
            static_cast<CGBitmapInfo>(kCGImageAlphaPremultipliedLast) | static_cast<CGBitmapInfo>(kCGBitmapByteOrder32Big));
        CGColorSpaceRelease(colorSpace);
        if (!context)
            return -5;

        int32_t status = 0;
        @try {
            [NSApplication sharedApplication];
            CGContextSetRGBFillColor(context, 1, 1, 1, 1);
            CGContextFillRect(context, CGRectMake(0, 0, 512, 40));
            CGContextScaleCTM(context, 2, 2);
            NSAppearance* appearance = [NSAppearance appearanceNamed:NSAppearanceNameAqua];
            [appearance performAsCurrentDrawingAppearance:^{
                [appearance _drawInRect:NSMakeRect(0, 0, 256, 20) context:context options:@{
                    widgetKey: widget,
                    valueKey: @(position < 0 ? 1 : std::min(std::nextafter(1.0, -1.0), position)),
                    sizeKey: size,
                    directionKey: direction,
                    scaleKey: @2,
                    stateKey: state,
                    orientationKey: orientation,
                    startKey: @(startTime),
                    timeKey: @(currentTime)
                }];
            }];
        } @catch (NSException* exception) {
            fprintf(stderr, "CoreUI clock probe: %s: %s\n", exception.name.UTF8String, exception.reason.UTF8String);
            status = -6;
        }
        CGContextRelease(context);
        *getterCalls = systemGetterCalls.load();
        return status;
    }
}
