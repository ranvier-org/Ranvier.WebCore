#include "../../providers/atspi/RanvierAtspi.h"
#include <stddef.h>

_Static_assert(sizeof(RvAtspiGeometry) == 24, "RvAtspiGeometry size");
_Static_assert(offsetof(RvAtspiGeometry, size) == 0, "size offset");
_Static_assert(offsetof(RvAtspiGeometry, screen_position_known) == 4, "screen_position_known offset");
_Static_assert(offsetof(RvAtspiGeometry, screen_x) == 8, "screen_x offset");
_Static_assert(offsetof(RvAtspiGeometry, screen_y) == 12, "screen_y offset");
_Static_assert(offsetof(RvAtspiGeometry, device_scale) == 16, "device_scale offset");

int main(void) { return 0; }
