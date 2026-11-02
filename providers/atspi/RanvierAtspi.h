#pragma once

#include "../../host/RanvierWebCoreAbi.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Optional Linux provider. All calls, native host operations and GMainContext dispatch use the host owner thread.
 * Release before destroying the host. The provider owns its accessibility callback until released. */
typedef struct {
    uint32_t size;
    int32_t screen_position_known;
    int32_t screen_x;
    int32_t screen_y;
    double device_scale;
} RvAtspiGeometry;

/* A NULL bus address discovers AT_SPI_BUS_ADDRESS or the session's org.a11y.Bus within two seconds. An explicit address
 * connects only to that bus. rv_run_loop_cycle pumps callbacks on the owner thread. name_length counts UTF-8 bytes;
 * D-Bus-inexpressible NUL/invalid UTF-8 becomes U+FFFD. Failure leaves *bridge zero. */
RV_EXPORT int32_t rv_atspi_bridge_create(RvHost*, const char* bus_address, const uint8_t* name, int32_t name_length,
    const RvAtspiGeometry*, uint64_t* bridge);
RV_EXPORT int32_t rv_atspi_bridge_set_geometry(uint64_t bridge, const RvAtspiGeometry*);
/* Copies the provider's unique D-Bus name using the existing byte-length/capacity convention. The application root
 * is /org/a11y/atspi/accessible/root. This module is a private prototype, outside the core native ABI allocation. */
RV_EXPORT int32_t rv_atspi_bridge_bus_name(uint64_t bridge, char* buffer, int32_t capacity, int32_t* length);
RV_EXPORT int32_t rv_atspi_bridge_release(uint64_t bridge);

#ifdef __cplusplus
}
#endif
