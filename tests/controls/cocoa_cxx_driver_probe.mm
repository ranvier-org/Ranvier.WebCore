#import <Foundation/Foundation.h>

extern "C" int ranvier_cxx_driver_probe()
{
    @autoreleasepool {
        try {
            if ([ @"driver" length ] != 6)
                return -1;
            throw 7;
        } catch (int value) {
            return value == 7 ? 0 : -2;
        }
    }
}
