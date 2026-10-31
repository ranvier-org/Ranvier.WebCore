struct CapabilityBuildFlag { const char* name; int value; };
#include "RanvierCapabilityCatalogue.inc"

static constexpr const char* capabilitySettingNames[] = {
    "scripts", "vm-entry-guard", "scroll-animation", "accelerated-compositing", "forced-compositing",
    "compositing-mode", "automatic-images", "media", "datalist", "download-attribute",
    "font-metric-overrides", "anchor-positioning", "device-scale", "viewport-width", "viewport-height",
    "paint-width", "paint-height", "webgl", "webgpu", "font-load-timing-override", "ignore-font-load-completions"
};
static constexpr const char* capabilityImageNames[] = {
    "image/png", "image/jpeg", "image/gif", "image/bmp", "image/x-icon", "image/webp", "image/avif", "image/jxl", "image/svg+xml"
};
static constexpr const char* capabilityFontNames[] = { "truetype", "opentype", "woff", "woff2", "collection", "truetype-variations", "opentype-variations", "woff-variations", "woff2-variations" };
static constexpr const char* capabilityFacilityNames[] = {
    "compositing", "presentation-d3d11", "angle", "gpu", "video", "web-audio", "media-stream", "media-recorder",
    "web-codecs", "encrypted-media", "webgl", "webgpu", "webxr", "network", "resource-callback",
    "crypto-digest", "crypto-other-algorithms", "sqlite", "indexeddb", "cache-storage", "service-worker",
    "shared-worker", "websocket", "webtransport", "file-system", "push", "inspector", "remote-inspector",
    "jsc-inspector", "jit", "dfg-jit", "ftl-jit", "webassembly", "webassembly-bbq-jit", "webassembly-omg-jit",
    "accessibility", "accessibility-uia", "accessibility-events", "clipboard", "clipboard-read-callback",
    "clipboard-write-callback", "drop", "drag-out", "popups", "tooltip", "input", "ime", "frame", "scroll",
    "speech-synthesis", "gamepad", "spellcheck", "pdfjs", "wk-web-extensions", "notifications", "diagnostics",
    "inspector-frontend", "cascade-diagnostics"
};

static constexpr const char* capabilityHostFacilityNames[] = { "clipboard", "drop", "tooltip", "input", "ime", "scroll" };

struct CapabilityResult {
    int facts[5] { -1, -1, -1, -1, -1 };
    int kind { 0 };
    double number { 0 };
    String text;
    void boolean(bool value) { kind = 1; number = value ? 1 : 0; }
    void numeric(double value) { kind = 2; number = value; }
};

template<size_t size> static bool capabilityContains(const char* const (&names)[size], const char* name)
{
    for (auto* candidate : names) {
        if (!std::strcmp(candidate, name))
            return true;
    }
    return false;
}

static int capabilityFlag(const char* name)
{
    for (auto& flag : capabilityBuildFlags) {
        if (!std::strcmp(flag.name + 6, name))
            return flag.value;
    }
    return -1;
}

static int capabilityImplementation(const char* enabled, const char* stub = nullptr)
{
    auto enable = enabled ? capabilityFlag(enabled) : 1;
    auto stubbed = stub ? capabilityFlag(stub) : 0;
    if (!enable || stubbed == 1)
        return 0;
    if (!enabled)
        return -1;
    return enable == 1 && stubbed == 0 ? 1 : -1;
}

static int capabilityInput(RvHost* host, int32_t category, const char* name)
{
    if (!host || !name)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (!liveHosts.contains(host) || category < 0 || category > 4 || !*name)
        return RV_ERR_UNSUPPORTED;
    for (auto* byte = reinterpret_cast<const unsigned char*>(name); *byte; ++byte) {
        if (*byte < 32 || *byte == 127)
            return RV_ERR_UNSUPPORTED;
    }
    return RV_OK;
}

static CapabilityResult capabilityQuery(RvHost& host, int category, const char* name)
{
    CapabilityResult result;
    if (!category) {
        if (capabilityContains(capabilityAbiNames, name))
            result.facts[0] = rv_abi_has(name) ? 1 : 0;
        return result;
    }
    if (category == 1 && capabilityContains(capabilitySettingNames, name)) {
        result.facts[0] = 1;
        auto& settings = host.page->settings();
        if (!std::strcmp(name, "scripts")) result.boolean(settings.isScriptEnabled());
        else if (!std::strcmp(name, "vm-entry-guard")) result.boolean(host.noScript.has_value());
        else if (!std::strcmp(name, "scroll-animation")) result.boolean(settings.scrollAnimatorEnabled());
        else if (!std::strcmp(name, "accelerated-compositing")) result.boolean(settings.acceleratedCompositingEnabled());
        else if (!std::strcmp(name, "forced-compositing")) result.boolean(settings.forceCompositingMode());
        else if (!std::strcmp(name, "automatic-images")) result.boolean(settings.loadsImagesAutomatically());
        else if (!std::strcmp(name, "datalist")) result.boolean(settings.dataListElementEnabled());
        else if (!std::strcmp(name, "download-attribute")) result.boolean(settings.downloadAttributeEnabled());
        else if (!std::strcmp(name, "font-metric-overrides")) result.boolean(settings.cssFontFaceMetricOverrideDescriptorsEnabled());
        else if (!std::strcmp(name, "anchor-positioning")) result.boolean(settings.cssAnchorPositioningEnabled());
        else if (!std::strcmp(name, "device-scale")) result.numeric(host.deviceScale);
        else if (!std::strcmp(name, "viewport-width")) result.numeric(host.size.width());
        else if (!std::strcmp(name, "viewport-height")) result.numeric(host.size.height());
        else if (!std::strcmp(name, "paint-width")) result.numeric(paintSize(host).width());
        else if (!std::strcmp(name, "paint-height")) result.numeric(paintSize(host).height());
        else if (!std::strcmp(name, "compositing-mode")) {
            result.kind = 3;
#if RANVIER_COMPOSITING
            result.text = host.compositingMode == RV_COMPOSITING_ALWAYS ? "always"_s : host.compositingMode == RV_COMPOSITING_WHEN_NEEDED ? "when-needed"_s : "off"_s;
#else
            result.text = "off"_s;
#endif
        }
        else if (!std::strcmp(name, "media")) {
#if ENABLE(VIDEO)
            result.boolean(settings.mediaEnabled());
#else
            result.facts[1] = 0;
            result.facts[2] = 0;
#endif
        }
        else if (!std::strcmp(name, "webgl")) {
#if ENABLE(WEBGL)
            result.boolean(settings.webGLEnabled());
#else
            result.facts[1] = 0;
            result.facts[2] = 0;
#endif
        }
        else if (!std::strcmp(name, "webgpu")) {
#if ENABLE(WEBGPU)
            result.boolean(settings.webGPUEnabled());
#else
            result.facts[1] = 0;
            result.facts[2] = 0;
#endif
        }
        else if (!std::strcmp(name, "font-load-timing-override")) result.numeric(static_cast<unsigned>(settings.fontLoadTimingOverride()));
        else if (!std::strcmp(name, "ignore-font-load-completions")) result.boolean(settings.shouldIgnoreFontLoadCompletions());
        if (result.kind) result.facts[1] = 1;
        if (result.kind == 1) result.facts[2] = result.number ? 1 : 0;
        return result;
    }
    if (category == 2) {
        auto mime = String::fromUTF8(name);
        if (mime.isNull() || !mime.contains('/')) return result;
        result.facts[0] = 1;
        result.facts[1] = MIMETypeRegistry::isSupportedImageVideoOrSVGMIMEType(mime) ? 1 : 0;
        result.boolean(result.facts[1]);
        return result;
    }
    if (category == 3) {
        if (!capabilityContains(capabilityFontNames, name)) return result;
        auto condition = makeString("font-format("_s, String::fromUTF8(name), ')').utf8();
        int32_t supported = 0;
        if (ranvier_dom_css_supports_1(reinterpret_cast<RvNode*>(&host.document()), reinterpret_cast<const uint8_t*>(condition.data()), condition.length(), &supported) != RV_OK)
            return result;
        result.facts[0] = 1;
        result.facts[1] = supported ? 1 : 0;
        result.boolean(supported);
        return result;
    }
    if (category != 4) return result;
    for (auto& flag : capabilityBuildFlags) {
        if (!std::strcmp(flag.name, name)) {
            if (flag.value >= 0) result.boolean(flag.value);
            return result;
        }
    }
    if (!capabilityContains(capabilityFacilityNames, name)) return result;
    struct Mapping { const char* name; const char* enable; const char* stub; };
    static constexpr Mapping mappings[] = {
        {"angle", nullptr, "USE_ANGLE_STUB"}, {"gpu", nullptr, "USE_GPU_STUB"},
        {"video", "ENABLE_VIDEO", nullptr}, {"web-audio", "ENABLE_WEB_AUDIO", nullptr},
        {"media-stream", "ENABLE_MEDIA_STREAM", nullptr}, {"media-recorder", "ENABLE_MEDIA_RECORDER", nullptr},
        {"web-codecs", "ENABLE_WEB_CODECS", nullptr}, {"encrypted-media", "ENABLE_ENCRYPTED_MEDIA", nullptr},
        {"webgl", "ENABLE_WEBGL", "USE_GPU_STUB"}, {"webgpu", "ENABLE_WEBGPU", "USE_BROWSER_API_STUB"},
        {"webxr", "ENABLE_WEBXR", "USE_BROWSER_API_STUB"}, {"network", nullptr, "USE_NETWORK_STUB"},
        {"crypto-other-algorithms", nullptr, "USE_CRYPTO_STUB"}, {"sqlite", nullptr, "USE_SQLITE_STUB"},
        {"indexeddb", nullptr, "USE_WEB_API_STUB"}, {"cache-storage", nullptr, "USE_WEB_API_STUB"},
        {"service-worker", nullptr, "USE_WEB_API_STUB"}, {"shared-worker", nullptr, "USE_WEB_API_STUB"},
        {"websocket", nullptr, "USE_WEB_API_STUB"}, {"push", nullptr, "USE_WEB_API_STUB"},
        {"webtransport", nullptr, "USE_BROWSER_API_STUB"}, {"file-system", nullptr, "USE_BROWSER_API_STUB"},
        {"inspector", nullptr, "USE_INSPECTOR_STUB"}, {"jsc-inspector", nullptr, "USE_JSC_INSPECTOR_STUB"},
        {"remote-inspector", "ENABLE_REMOTE_INSPECTOR", nullptr}, {"jit", "ENABLE_JIT", nullptr},
        {"dfg-jit", "ENABLE_DFG_JIT", nullptr}, {"ftl-jit", "ENABLE_FTL_JIT", nullptr},
        {"webassembly", "ENABLE_WEBASSEMBLY", nullptr}, {"webassembly-bbq-jit", "ENABLE_WEBASSEMBLY_BBQJIT", nullptr},
        {"webassembly-omg-jit", "ENABLE_WEBASSEMBLY_OMGJIT", nullptr}, {"speech-synthesis", "ENABLE_SPEECH_SYNTHESIS", nullptr},
        {"gamepad", "ENABLE_GAMEPAD", nullptr}, {"spellcheck", "ENABLE_SPELLCHECK", nullptr},
        {"pdfjs", "ENABLE_PDFJS", nullptr}, {"wk-web-extensions", "ENABLE_WK_WEB_EXTENSIONS", nullptr},
        {"notifications", "ENABLE_NOTIFICATIONS", nullptr}
    };
    for (auto& mapping : mappings) {
        if (!std::strcmp(mapping.name, name)) result.facts[1] = capabilityImplementation(mapping.enable, mapping.stub);
    }
    if (!std::strcmp(name, "compositing")) {
#if RANVIER_COMPOSITING
        result.facts[1] = 1;
#else
        result.facts[1] = 0;
#endif
    }
    if (!std::strcmp(name, "presentation-d3d11")) {
#if RANVIER_COMPOSITING && defined(_WIN32)
        result.facts[1] = 1;
#else
        result.facts[1] = 0;
#endif
    }
    if (!std::strcmp(name, "crypto-digest") && capabilityFlag("USE_CRYPTO_STUB") == 1) result.facts[1] = 1;
    if (!std::strcmp(name, "video")) {
#if ENABLE(VIDEO)
        result.boolean(host.page->settings().mediaEnabled());
#endif
    }
    if (!std::strcmp(name, "webgl")) {
#if ENABLE(WEBGL)
        result.boolean(host.page->settings().webGLEnabled());
#endif
    }
    if (!std::strcmp(name, "webgpu")) {
#if ENABLE(WEBGPU)
        result.boolean(host.page->settings().webGPUEnabled());
#endif
    }
    if (!std::strcmp(name, "resource-callback")) { result.facts[1] = 1; result.boolean(!!host.resourceHandler); }
    else if (!std::strcmp(name, "clipboard-read-callback")) { result.facts[1] = 1; result.boolean(!!host.clipboardRead); }
    else if (!std::strcmp(name, "clipboard-write-callback")) { result.facts[1] = 1; result.boolean(!!host.clipboardWrite); }
    else if (!std::strcmp(name, "popups")) { result.facts[1] = 1; result.boolean(!!host.popupCallback); }
    else if (!std::strcmp(name, "drag-out")) { result.facts[1] = 1; result.boolean(!!host.dragStartCallback); }
    else if (!std::strcmp(name, "frame")) { result.facts[1] = 1; result.boolean(!!host.frameCallback); }
    else if (!std::strcmp(name, "accessibility")) { result.facts[1] = 1; result.boolean(host.accessibility); }
    else if (!std::strcmp(name, "accessibility-events")) { result.facts[1] = rv_abi_has(name); result.boolean(!!host.axCallback); }
    else if (!std::strcmp(name, "accessibility-uia")) result.facts[1] = rv_abi_has(name);
    else if (!std::strcmp(name, "diagnostics")) { result.facts[1] = 1; result.boolean(host.diagnostics); }
    else if (!std::strcmp(name, "cascade-diagnostics")) { result.facts[1] = 1; result.boolean(host.diagnostics); }
    // No flavor ships a developer-tools frontend (WebInspectorUI) or connects one to the page's inspector controller.
    else if (!std::strcmp(name, "inspector-frontend")) { result.facts[1] = 0; result.facts[4] = 0; }
    else if (capabilityContains(capabilityHostFacilityNames, name)) result.facts[1] = 1;
    if (result.kind == 1) result.facts[2] = result.number ? 1 : 0;
    return result;
}

int32_t rv_capability_count(int32_t category)
{
    switch (category) {
    case 0: return std::size(capabilityAbiNames);
    case 1: return std::size(capabilitySettingNames);
    case 2: return std::size(capabilityImageNames);
    case 3: return std::size(capabilityFontNames);
    case 4: return std::size(capabilityFacilityNames) + std::size(capabilityBuildFlags);
    default: return RV_ERR_UNSUPPORTED;
    }
}

int32_t rv_capability_name_at(int32_t category, int32_t index, char* buffer, int32_t capacity, int32_t* length)
{
    auto count = rv_capability_count(category);
    if (count < 0 || index < 0 || index >= count || capacity < 0) return RV_ERR_UNSUPPORTED;
    const char* name = nullptr;
    switch (category) {
    case 0: name = capabilityAbiNames[index]; break;
    case 1: name = capabilitySettingNames[index]; break;
    case 2: name = capabilityImageNames[index]; break;
    case 3: name = capabilityFontNames[index]; break;
    case 4: name = index < static_cast<int>(std::size(capabilityFacilityNames)) ? capabilityFacilityNames[index] : capabilityBuildFlags[index - std::size(capabilityFacilityNames)].name; break;
    }
    return copyString(String::fromUTF8(name), buffer, capacity, length);
}

int32_t rv_host_capability_fact(RvHost* host, int32_t category, const char* name, int32_t dimension, int32_t* fact)
{
    if (!fact) return RV_ERR_NULL_ARGUMENT;
    auto status = capabilityInput(host, category, name);
    if (status) return status;
    if (dimension < 0 || dimension > 4) return RV_ERR_UNSUPPORTED;
    *fact = capabilityQuery(*host, category, name).facts[dimension];
    return RV_OK;
}

int32_t rv_host_capability_value_kind(RvHost* host, int32_t category, const char* name, int32_t* kind)
{
    if (!kind) return RV_ERR_NULL_ARGUMENT;
    auto status = capabilityInput(host, category, name);
    if (status) return status;
    *kind = capabilityQuery(*host, category, name).kind;
    return RV_OK;
}

int32_t rv_host_capability_value_number(RvHost* host, int32_t category, const char* name, double* number)
{
    if (!number) return RV_ERR_NULL_ARGUMENT;
    auto status = capabilityInput(host, category, name);
    if (status) return status;
    auto result = capabilityQuery(*host, category, name);
    if (result.kind != 1 && result.kind != 2) return RV_ERR_UNSUPPORTED;
    *number = result.number;
    return RV_OK;
}

int32_t rv_host_capability_value_text(RvHost* host, int32_t category, const char* name, char* buffer, int32_t capacity, int32_t* length)
{
    if (!length) return RV_ERR_NULL_ARGUMENT;
    auto status = capabilityInput(host, category, name);
    if (status) return status;
    if (capacity < 0) return RV_ERR_UNSUPPORTED;
    auto result = capabilityQuery(*host, category, name);
    if (result.kind != 3) return RV_ERR_UNSUPPORTED;
    return copyString(result.text, buffer, capacity, length);
}
