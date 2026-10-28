// Include the identical provider implementation in the fixture translation unit so the test can
// inspect its internal ownership cache. The production ABI and DLL have no test diagnostics.
#define RV_UIA_CACHE_PROBE 1
#include "../../host/RanvierWebCoreUia.cpp"
#include "Acceptance.cpp"
