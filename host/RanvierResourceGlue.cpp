#include "config.h"
#include "RanvierResourceGlue.h"
#include "CachedImage.h"
#include "Document.h"
#include "DocumentInlines.h"
#include "HTMLImageElement.h"
#include "HTMLElementTypeHelpers.h"
#include "Image.h"
#include "ImageLoader.h"
#include "Node.h"
#include "SVGImageElement.h"
#include "SVGElementTypeHelpers.h"
#include <unordered_map>
#include <wtf/MainThread.h>
#include <wtf/RefCounted.h>
#include <wtf/RunLoop.h>
#include <wtf/TZoneMallocInlines.h>
#include <wtf/WeakPtr.h>

using namespace WebCore;

namespace {

Document* documentFromHandle(RvNode* handle)
{
    return handle ? dynamicDowncast<Document>(reinterpret_cast<Node*>(handle)) : nullptr;
}

int32_t outcomeFor(ImageDecodeResult result)
{
    switch (result) {
    case ImageDecodeResult::Decoded:
        return RV_RESOURCE_SUCCEEDED;
    case ImageDecodeResult::SourceChanged:
    case ImageDecodeResult::InactiveDocument:
        return RV_RESOURCE_INVALIDATED;
    case ImageDecodeResult::Canceled:
        return RV_RESOURCE_CANCELLED;
    case ImageDecodeResult::AccessControlError:
    case ImageDecodeResult::MissingSource:
    case ImageDecodeResult::LoadError:
        return RV_RESOURCE_LOAD_FAILED;
    case ImageDecodeResult::DecodeError:
        return RV_RESOURCE_DECODE_FAILED;
    }
    return RV_RESOURCE_LOAD_FAILED;
}

struct ImageOperation final : RefCounted<ImageOperation>, CanMakeSingleThreadWeakPtr<ImageOperation> {
    WTF_MAKE_TZONE_ALLOCATED(ImageOperation);

public:
    RefPtr<Document> document;
    RefPtr<Element> target;
    RvResourceCompletion callback;
    void* context;
    bool terminal { false };
    bool starting { false };
    bool pending { false };
    int32_t pendingOutcome { 0 };
    int32_t pendingWidth { 0 };
    int32_t pendingHeight { 0 };

    ImageOperation(Document& document, Element& target, RvResourceCompletion callback, void* context)
        : document(&document)
        , target(&target)
        , callback(callback)
        , context(context)
    {
    }

    // A terminal operation holds no engine object. A waiter still queued in the ImageLoader holds only a weak pointer.
    void detach()
    {
        target = nullptr;
        document = nullptr;
    }

    void finish(int32_t outcome)
    {
        if (terminal)
            return;
        Ref protectThis { *this };
        terminal = true;
        int32_t width = 0;
        int32_t height = 0;
        if (outcome == RV_RESOURCE_SUCCEEDED && target) {
            if (auto* element = dynamicDowncast<HTMLImageElement>(*target)) {
                width = element->naturalWidth();
                height = element->naturalHeight();
            } else if (auto* element = dynamicDowncast<SVGImageElement>(*target)) {
                if (CachedImage* image = element->cachedImage(); image && image->image()) {
                    auto size = expandedIntSize(image->image()->size());
                    width = size.width();
                    height = size.height();
                }
            }
        }
        detach();
        pending = true;
        pendingOutcome = outcome;
        pendingWidth = width;
        pendingHeight = height;
        if (!starting) {
            flush();
            return;
        }
        // A terminal reached inside ranvier_resource_decode_image is delivered on a later run-loop turn.
        RunLoop::mainSingleton().dispatch([weak = SingleThreadWeakPtr<ImageOperation> { *this }] {
            if (RefPtr operation = weak.get())
                operation->flush();
        });
    }

    void flush()
    {
        if (!std::exchange(pending, false))
            return;
        auto completion = std::exchange(callback, nullptr);
        if (completion)
            completion(context, pendingOutcome, pendingWidth, pendingHeight);
    }

    void start()
    {
        starting = true;
        // The ImageLoader settles the waiter at the points where it settles decode() promises (patch 0031).
        Function<void(ImageDecodeResult)> waiter = [weak = SingleThreadWeakPtr<ImageOperation> { *this }](ImageDecodeResult result) {
            if (RefPtr operation = weak.get())
                operation->finish(outcomeFor(result));
        };
        if (auto* element = dynamicDowncast<HTMLImageElement>(*target))
            element->decode(WTF::move(waiter));
        else
            downcast<SVGImageElement>(*target).decode(WTF::move(waiter));
        starting = false;
    }
};

WTF_MAKE_TZONE_ALLOCATED_IMPL(ImageOperation);

std::unordered_map<uint64_t, Ref<ImageOperation>>& operations()
{
    static NeverDestroyed<std::unordered_map<uint64_t, Ref<ImageOperation>>> values;
    return values;
}

uint64_t nextOperation = 1;

void releaseOperation(uint64_t operation, int32_t outcome)
{
    auto found = operations().find(operation);
    if (found == operations().end())
        return;
    Ref value = found->second;
    operations().erase(found);
    value->finish(outcome);
    value->flush();
}

}

int32_t ranvier_resource_decode_image(RvNode* documentHandle, RvNode* targetHandle, RvResourceCompletion callback, void* context, uint64_t* operation)
{
    if (!documentHandle || !targetHandle || !callback || !operation)
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    auto* document = documentFromHandle(documentHandle);
    auto* target = dynamicDowncast<Element>(reinterpret_cast<Node*>(targetHandle));
    if (!document || !target || &target->document() != document || !document->window()
        || (!is<HTMLImageElement>(*target) && !is<SVGImageElement>(*target)))
        return RV_ERR_UNSUPPORTED;
    if (!nextOperation)
        return RV_ERR_UNSUPPORTED;
    Ref value = adoptRef(*new ImageOperation(*document, *target, callback, context));
    *operation = nextOperation++;
    operations().emplace(*operation, value.copyRef());
    value->start();
    return RV_OK;
}

int32_t ranvier_resource_cancel(uint64_t operation)
{
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    auto found = operations().find(operation);
    if (found != operations().end()) {
        Ref value = found->second;
        value->finish(RV_RESOURCE_CANCELLED);
        value->flush();
    }
    return RV_OK;
}

int32_t ranvier_resource_release(uint64_t operation)
{
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    releaseOperation(operation, RV_RESOURCE_CANCELLED);
    return RV_OK;
}

void ranvier_resource_invalidate_document(RvNode* handle)
{
    if (!WTF::isMainThread())
        return;
    auto* document = documentFromHandle(handle);
    if (!document)
        return;
    Vector<uint64_t> invalidated;
    for (auto& entry : operations()) {
        if (entry.second->document == document)
            invalidated.append(entry.first);
    }
    for (auto operation : invalidated)
        releaseOperation(operation, RV_RESOURCE_INVALIDATED);
}
