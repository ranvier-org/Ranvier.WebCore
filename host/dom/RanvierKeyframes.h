// The keyframe transport of the generated Web Animations functions (gen/RanvierKeyframes.idl), converted to the
// JavaScript keyframes object WebKit's keyframe processing takes. Compiled into WebCore with the glue.
#pragma once

#include "Exception.h"
#include "ExceptionOr.h"
#include "JSCompositeOperationOrAuto.h"
#include "JSDOMGlobalObject.h"
#include "KeyframeEffect.h"
#include <JavaScriptCore/TopExceptionScope.h>
#include <JavaScriptCore/ErrorInstance.h>
#include <JavaScriptCore/JSArray.h>
#include <JavaScriptCore/JSGlobalObjectInlines.h>
#include <JavaScriptCore/JSObjectInlines.h>
#include <JavaScriptCore/ObjectConstructor.h>
#include <JavaScriptCore/StrongInlines.h>
#include <wtf/Vector.h>
#include <wtf/text/WTFString.h>

namespace Ranvier {

struct KeyframeProperty {
    String name;
    String value;
};

struct Keyframe {
    std::optional<double> offset;
    String easing;
    String composite;
    Vector<KeyframeProperty> properties;
};

// One computed keyframe of KeyframeEffect.getKeyframes() (gen/RanvierKeyframes.idl).
struct ComputedKeyframe {
    std::optional<double> offset;
    double computedOffset { 0 };
    String easing;
    String composite;
    Vector<KeyframeProperty> properties;
};

// The computed keyframes WebKit's getKeyframes binding returns: custom properties by name, then each property by its
// IDL attribute name, with its string value. An offset that is not a number is null.
inline Vector<ComputedKeyframe> computedKeyframes(WebCore::KeyframeEffect& effect)
{
    return effect.getKeyframes().map([](auto& keyframe) {
        ComputedKeyframe result;
        if (auto* offset = std::get_if<double>(&keyframe.offset))
            result.offset = *offset;
        result.computedOffset = keyframe.computedOffset;
        result.easing = keyframe.easing;
        result.composite = WebCore::convertEnumerationToString(keyframe.composite);
        for (auto& [name, value] : keyframe.customStyleStrings)
            result.properties.append({ name, value });
        for (auto& [property, value] : keyframe.styleStrings)
            result.properties.append({ WebCore::KeyframeEffect::CSSPropertyIDToIDLAttributeName(property), value });
        return result;
    });
}

// The JavaScript array of plain objects a script would pass: one object per keyframe, holding offset, easing and
// composite when present and each property as a string. Null keyframes give a null object. The caller holds the
// JavaScript lock; the objects are created in the global object without entering the VM.
inline JSC::Strong<JSC::JSObject> keyframesObject(JSC::JSGlobalObject& global, std::optional<Vector<Keyframe>>&& keyframes)
{
    auto& vm = global.vm();
    if (!keyframes)
        return { };
    auto* array = JSC::constructEmptyArray(&global, nullptr, keyframes->size());
    RELEASE_ASSERT(array);
    unsigned index = 0;
    for (auto& keyframe : *keyframes) {
        auto* object = JSC::constructEmptyObject(&global);
        for (auto& property : keyframe.properties)
            object->putDirect(vm, JSC::Identifier::fromString(vm, property.name), JSC::jsString(vm, property.value));
        if (keyframe.offset)
            object->putDirect(vm, JSC::Identifier::fromString(vm, "offset"_s), JSC::jsNumber(*keyframe.offset));
        if (!keyframe.easing.isNull())
            object->putDirect(vm, JSC::Identifier::fromString(vm, "easing"_s), JSC::jsString(vm, keyframe.easing));
        if (!keyframe.composite.isNull())
            object->putDirect(vm, JSC::Identifier::fromString(vm, "composite"_s), JSC::jsString(vm, keyframe.composite));
        array->putDirectIndex(&global, index++, object);
    }
    return JSC::Strong<JSC::JSObject>(vm, array);
}

// Calls the member with the keyframes object, under the JavaScript lock and an exception scope. WebKit's keyframe
// processing reports some errors only as an exception left on the VM, as a script caller would see it thrown; that
// exception becomes the call's exception, by its WebIDL error name, and leaves the VM clear.
template<typename Call>
auto keyframesCall(JSC::JSGlobalObject& global, std::optional<Vector<Keyframe>>&& keyframes, Call&& call)
    -> decltype(call(JSC::Strong<JSC::JSObject> { }))
{
    auto& vm = global.vm();
    JSC::JSLockHolder lock(vm);
    auto scope = DECLARE_TOP_EXCEPTION_SCOPE(vm);
    auto result = call(keyframesObject(global, WTF::move(keyframes)));
    if (auto* exception = scope.exception()) {
        auto code = WebCore::ExceptionCode::TypeError;
        if (auto* error = dynamicDowncast<JSC::ErrorInstance>(exception->value())) {
            if (error->errorType() == JSC::ErrorType::RangeError)
                code = WebCore::ExceptionCode::RangeError;
            else if (error->errorType() == JSC::ErrorType::SyntaxError)
                code = WebCore::ExceptionCode::SyntaxError;
        }
        scope.clearException();
        if (!result.hasException())
            return WebCore::Exception { code, "The keyframes are invalid."_s };
    }
    return result;
}

} // namespace Ranvier
