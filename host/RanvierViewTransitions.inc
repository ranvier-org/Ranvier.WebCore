#include "DOMException.h"
#include "JSDOMException.h"
#include "JSDOMPromise.h"
#include "JSDOMPromiseDeferred.h"
#include "ViewTransition.h"
#include "ViewTransitionUpdateCallback.h"
#include <JavaScriptCore/ErrorInstance.h>

namespace {

class HostViewTransitionUpdateCallback final : public ViewTransitionUpdateCallback {
public:
    static Ref<HostViewTransitionUpdateCallback> create(Document& document, RvViewTransitionUpdate update,
        void* context, RvCustomEffectRelease release)
    {
        return adoptRef(*new HostViewTransitionUpdateCallback(document, update, context, release));
    }

    ~HostViewTransitionUpdateCallback()
    {
        live().remove(this);
        if (m_release)
            m_release(m_context);
    }

    static HashSet<HostViewTransitionUpdateCallback*>& live()
    {
        static NeverDestroyed<HashSet<HostViewTransitionUpdateCallback*>> value;
        return value;
    }

    void revoke() { m_update = nullptr; }

private:
    HostViewTransitionUpdateCallback(Document& document, RvViewTransitionUpdate update, void* context,
        RvCustomEffectRelease release)
        : ViewTransitionUpdateCallback(&document)
        , m_update(update)
        , m_context(context)
        , m_release(release)
    {
        live().add(this);
    }

    CallbackResult<Ref<DOMPromise>> invoke() final
    {
        RefPtr document = dynamicDowncast<Document>(scriptExecutionContext());
        if (!document || !canInvokeCallback())
            return CallbackResultType::UnableToExecute;
        auto [promise, deferred] = createPromiseAndWrapper(*document);
        if (!m_update || m_update(m_context))
            deferred->reject(ExceptionCode::TypeError);
        else
            deferred->resolve();
        return WTF::move(promise);
    }

    bool hasCallback() const final { return true; }
    RvViewTransitionUpdate m_update;
    void* m_context;
    RvCustomEffectRelease m_release;
};

struct TransitionObserver : RefCounted<TransitionObserver> {
    RefPtr<ViewTransition> transition;
    WeakPtr<Document, WeakPtrImplWithEventTargetData> document;
    RvViewTransitionSettled callback;
    void* context;
    bool delivered[3] { false, false, false };

    TransitionObserver(Document& document, ViewTransition& transition, RvViewTransitionSettled callback, void* context)
        : transition(&transition), document(document), callback(callback), context(context) { }

    void invalidate() { callback = nullptr; transition = nullptr; document = nullptr; }
};

Vector<Ref<TransitionObserver>>& transitionObservers()
{
    static NeverDestroyed<Vector<Ref<TransitionObserver>>> value;
    return value;
}

String transitionRejectionName(Document& document, DOMPromise& promise)
{
    auto value = promise.result();
    if (auto* exception = JSDOMException::toWrapped(document.vm(), value))
        return exception->name();
    if (auto* error = dynamicDowncast<JSC::ErrorInstance>(value)) {
        if (error->errorType() == JSC::ErrorType::TypeError)
            return "TypeError"_s;
    }
    return "Error"_s;
}

}

RvViewTransitionUpdateCallback* ranvier_view_transition_update_callback_create(RvNode* documentHandle,
    RvViewTransitionUpdate update, void* context, RvCustomEffectRelease release)
{
    auto* document = documentOf(documentHandle);
    if (!document || !update || !isMainThread())
        return nullptr;
    ViewTransitionUpdateCallback* callback = &HostViewTransitionUpdateCallback::create(*document, update, context, release).leakRef();
    return reinterpret_cast<RvViewTransitionUpdateCallback*>(callback);
}

int32_t ranvier_view_transition_update_callback_revoke(RvViewTransitionUpdateCallback* handle)
{
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    if (!isMainThread())
        return RV_ERR_WRONG_THREAD;
    auto* callback = static_cast<HostViewTransitionUpdateCallback*>(reinterpret_cast<ViewTransitionUpdateCallback*>(handle));
    if (!HostViewTransitionUpdateCallback::live().contains(callback))
        return RV_ERR_WRONG_INTERFACE;
    callback->revoke();
    return RV_OK;
}

int32_t ranvier_view_transition_observe(RvNode* documentHandle, RvViewTransition* handle, RvViewTransitionSettled callback,
    void* context, RvViewTransitionObserver** result)
{
    if (!documentHandle || !handle || !callback || !result)
        return RV_ERR_NULL_ARGUMENT;
    if (!isMainThread())
        return RV_ERR_WRONG_THREAD;
    auto* document = documentOf(documentHandle);
    auto& transition = *reinterpret_cast<ViewTransition*>(handle);
    if (transition.document() != document)
        return RV_ERR_WRONG_HOST;
    Ref observer = adoptRef(*new TransitionObserver(*document, transition, callback, context));
    *result = reinterpret_cast<RvViewTransitionObserver*>(observer.ptr());
    transitionObservers().append(WTF::move(observer));
    return RV_OK;
}

void ranvier_view_transition_observer_release(RvViewTransitionObserver* handle)
{
    if (!handle || !isMainThread())
        return;
    auto* observer = reinterpret_cast<TransitionObserver*>(handle);
    observer->invalidate();
    transitionObservers().removeFirstMatching([&](auto& candidate) { return candidate.ptr() == observer; });
}

void ranvier_view_transitions_deliver()
{
    auto observers = transitionObservers();
    for (auto& observer : observers) {
        for (int32_t kind = 0; kind < 3; ++kind) {
            if (!observer->callback || !observer->document || !observer->transition)
                break;
            if (observer->delivered[kind])
                continue;
            Ref transition = *observer->transition;
            auto& promise = kind == 0 ? transition->updateCallbackDone() : kind == 1 ? transition->ready() : transition->finished();
            auto status = promise.status();
            if (status == DOMPromise::Status::Pending)
                continue;
            observer->delivered[kind] = true;
            CString error;
            if (status == DOMPromise::Status::Rejected)
                error = transitionRejectionName(*observer->document, promise).utf8();
            observer->callback(observer->context, kind, error.isNull() ? nullptr : error.data());
        }
    }
}

void ranvier_view_transitions_invalidate_document(RvNode* documentHandle)
{
    auto* document = documentOf(documentHandle);
    for (auto* callback : HostViewTransitionUpdateCallback::live()) {
        if (callback->scriptExecutionContext() == document)
            callback->revoke();
    }
    for (auto& observer : transitionObservers()) {
        if (observer->document.get() == document)
            observer->invalidate();
    }
}
