#include "config.h"
#include "RanvierPointerGlue.h"
#include "dom/RanvierDomGlue.h"

#if ENABLE(POINTER_LOCK)
#include "DOMException.h"
#include "Document.h"
#include "DocumentPage.h"
#include "Element.h"
#include "NodeDocument.h"
#include "JSDOMException.h"
#include "JSDOMGlobalObject.h"
#include "JSDOMPromiseDeferred.h"
#include "Page.h"
#include "PointerLockController.h"
#include "PointerLockOptions.h"
#include <JavaScriptCore/JSLock.h>
#include <JavaScriptCore/JSPromise.h>
#endif
#if ENABLE(TOUCH_EVENTS)
#include "Touch.h"
#endif
#include <wtf/MainThread.h>

using namespace WebCore;

#if ENABLE(POINTER_LOCK)
namespace {

Node* nodeOf(RvNode* handle)
{
    return reinterpret_cast<Node*>(handle);
}

Page* pageOf(Document* document)
{
    return document ? document->page() : nullptr;
}

}
#endif

int32_t ranvier_element_request_pointer_lock(RvNode* handle, int32_t unadjustedMovement)
{
#if ENABLE(POINTER_LOCK)
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    if (!isMainThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr element = dynamicDowncast<Element>(*nodeOf(handle));
    if (!element)
        return RV_ERR_NOT_ELEMENT;
    Ref document = element->document();
    if (!pageOf(document.ptr()))
        return RV_ERR_UNSUPPORTED;
    auto* globalObject = dynamicDowncast<JSDOMGlobalObject>(document->globalObject());
    if (!globalObject)
        return RV_ERR_UNSUPPORTED;
    JSC::JSLockHolder lock(globalObject->vm());
    RefPtr deferred = DeferredPromise::create(*globalObject, DeferredPromise::Mode::RetainPromiseOnResolve);
    if (!deferred)
        return RV_ERR_UNSUPPORTED;
    PointerLockOptions options;
    options.unadjustedMovement = unadjustedMovement;
    element->requestPointerLock(WTF::move(options), *deferred);
    // The engine rejects a request it refuses before it asks the embedder, so a rejection is visible here.
    auto* promise = dynamicDowncast<JSC::JSPromise>(deferred->promise());
    if (!promise || promise->status() != JSC::JSPromise::Status::Rejected)
        return RV_OK;
    promise->markAsHandled();
    if (auto* exception = dynamicDowncast<JSDOMException>(promise->result())) {
        auto& wrapped = exception->wrapped();
        for (auto code : { ExceptionCode::NotAllowedError, ExceptionCode::WrongDocumentError, ExceptionCode::SecurityError,
            ExceptionCode::NotSupportedError, ExceptionCode::InvalidStateError }) {
            if (wrapped.name() == StringView { DOMException::name(code) })
                return Ranvier::recordException(Exception { code, wrapped.message() });
        }
    }
    return Ranvier::recordException(Exception { ExceptionCode::UnknownError });
#else
    UNUSED_PARAM(handle);
    UNUSED_PARAM(unadjustedMovement);
    return RV_ERR_UNSUPPORTED;
#endif
}

int32_t ranvier_document_exit_pointer_lock(RvNode* handle)
{
#if ENABLE(POINTER_LOCK)
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    if (!isMainThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr document = dynamicDowncast<Document>(*nodeOf(handle));
    if (!document)
        return RV_ERR_WRONG_INTERFACE;
    if (!pageOf(document.get()))
        return RV_ERR_UNSUPPORTED;
    document->exitPointerLock();
    return RV_OK;
#else
    UNUSED_PARAM(handle);
    return RV_ERR_UNSUPPORTED;
#endif
}

int32_t ranvier_pointer_lock_state(RvNode* handle, int32_t* state, RvNode** element)
{
#if ENABLE(POINTER_LOCK)
    if (!handle || !state)
        return RV_ERR_NULL_ARGUMENT;
    if (!isMainThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr document = dynamicDowncast<Document>(*nodeOf(handle));
    if (!document)
        return RV_ERR_WRONG_INTERFACE;
    RefPtr page = pageOf(document.get());
    if (!page)
        return RV_ERR_UNSUPPORTED;
    auto& controller = page->pointerLockController();
    RefPtr target = controller.element();
    *state = !target ? RV_POINTER_LOCK_NONE : controller.lockPending() ? RV_POINTER_LOCK_PENDING : RV_POINTER_LOCK_LOCKED;
    if (element) {
        if (target)
            target->ref();
        *element = reinterpret_cast<RvNode*>(target.get());
    }
    return RV_OK;
#else
    UNUSED_PARAM(handle);
    UNUSED_PARAM(state);
    UNUSED_PARAM(element);
    return RV_ERR_UNSUPPORTED;
#endif
}

int32_t ranvier_touch_geometry(RvTouch* handle, RvTouchGeometry* geometry)
{
#if ENABLE(TOUCH_EVENTS)
    if (!handle || !geometry)
        return RV_ERR_NULL_ARGUMENT;
    if (!isMainThread())
        return RV_ERR_WRONG_THREAD;
    if (geometry->size < static_cast<int32_t>(sizeof(RvTouchGeometry)))
        return RV_ERR_UNSUPPORTED;
    auto& touch = *reinterpret_cast<Touch*>(handle);
    geometry->radiusX = touch.webkitRadiusX();
    geometry->radiusY = touch.webkitRadiusY();
    geometry->rotationAngle = touch.webkitRotationAngle();
    geometry->force = touch.webkitForce();
    return RV_OK;
#else
    UNUSED_PARAM(handle);
    UNUSED_PARAM(geometry);
    return RV_ERR_UNSUPPORTED;
#endif
}

int32_t ranvier_pointer_lock_lose(RvNode* handle)
{
#if ENABLE(POINTER_LOCK)
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    if (!isMainThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr document = dynamicDowncast<Document>(*nodeOf(handle));
    if (!document)
        return RV_ERR_WRONG_INTERFACE;
    RefPtr page = pageOf(document.get());
    if (!page)
        return RV_ERR_UNSUPPORTED;
    auto& controller = page->pointerLockController();
    if (controller.element() && !controller.lockPending())
        controller.didLosePointerLock();
    return RV_OK;
#else
    UNUSED_PARAM(handle);
    return RV_ERR_UNSUPPORTED;
#endif
}
