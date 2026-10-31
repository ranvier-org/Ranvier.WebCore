#include "config.h"
#include "RanvierResourceGlue.h"
#include "BitmapImage.h"
#include "CachedImage.h"
#include "CachedImageClient.h"
#include "CachedResourceHandle.h"
#include "Document.h"
#include "DocumentInlines.h"
#include "HTMLImageElement.h"
#include "HTMLElementTypeHelpers.h"
#include "Node.h"
#include "SVGImageElement.h"
#include "SVGElementTypeHelpers.h"
#include "Timer.h"
#include <unordered_map>
#include <wtf/MainThread.h>
#include <wtf/RefCounted.h>
#include <wtf/TZoneMallocInlines.h>
#include <wtf/RunLoop.h>
#include <wtf/WeakPtr.h>

using namespace WebCore;

namespace {

struct ImageOperation;
using WeakOperation = SingleThreadWeakPtr<CachedResourceClient>;
RefPtr<ImageOperation> lock(const WeakOperation&);

CachedImage* cachedImage(Element& target)
{
    if (auto* image = dynamicDowncast<HTMLImageElement>(target))
        return image->cachedImage();
    if (auto* image = dynamicDowncast<SVGImageElement>(target))
        return image->cachedImage();
    return nullptr;
}

// The attributes whose change makes ImageLoader select a new image request.
Vector<AtomString> sourceAttributes(Element& target)
{
    Vector<AtomString> values;
    for (auto name : { "src"_s, "srcset"_s, "sizes"_s, "href"_s, "xlink:href"_s, "crossorigin"_s, "referrerpolicy"_s })
        values.append(target.getAttribute(AtomString { name }));
    return values;
}

Document* documentFromHandle(RvNode* handle)
{
    return handle ? dynamicDowncast<Document>(reinterpret_cast<Node*>(handle)) : nullptr;
}

struct ImageOperation final : CachedImageClient, RefCounted<ImageOperation> {
    WTF_MAKE_TZONE_ALLOCATED(ImageOperation);

public:
    void ref() const final { RefCounted::ref(); }
    void deref() const final { RefCounted::deref(); }

    RefPtr<Document> document;
    RefPtr<Element> target;
    CachedResourceHandle<CachedImage> image;
    Vector<AtomString> sources;
    std::unique_ptr<Timer> generationCheck;
    RvResourceCompletion callback;
    void* context;
    bool terminal { false };
    bool decoding { false };
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

    ~ImageOperation() { detach(); }

    // A detached operation holds no engine object, so a terminal operation keeps no document alive.
    void detach()
    {
        // Stopped, not destroyed: detach can run inside the timer's own callback.
        if (generationCheck)
            generationCheck->stop();
        if (image)
            image->removeClient(*this);
        image = nullptr;
        target = nullptr;
        document = nullptr;
    }

    bool validGeneration()
    {
        if (!document || !target)
            return false;
        return sourceAttributes(*target) == sources && &target->document() == document.get()
            && document->window() && cachedImage(*target) == image.get();
    }

    void finish(int32_t outcome)
    {
        if (terminal)
            return;
        Ref protectThis { *this };
        if (outcome == RV_RESOURCE_SUCCEEDED && !validGeneration())
            outcome = RV_RESOURCE_INVALIDATED;
        terminal = true;
        int32_t width = 0;
        int32_t height = 0;
        if (outcome == RV_RESOURCE_SUCCEEDED) {
            if (auto* element = dynamicDowncast<HTMLImageElement>(*target)) {
                width = element->naturalWidth();
                height = element->naturalHeight();
            } else if (RefPtr decoded = image ? image->image() : nullptr) {
                auto size = expandedIntSize(decoded->size());
                width = size.width();
                height = size.height();
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
        RunLoop::mainSingleton().dispatch([weak = WeakOperation { *this }] {
            if (auto operation = lock(weak))
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
        startObserving();
        starting = false;
    }

    void startObserving()
    {
        document->updateLayoutIgnorePendingStylesheets();
        sources = sourceAttributes(*target);
        image = cachedImage(*target);
        if (!image) {
            finish(RV_RESOURCE_LOAD_FAILED);
            return;
        }
        // Mutation observers deliver at a microtask checkpoint, which a host without VM entry never performs
        // (MicrotaskQueue::performMicrotaskCheckpoint returns while disallowVMEntryCount is set), so a run-loop timer
        // ends the operation once the source attributes, the selected CachedImage or the document change.
        generationCheck = makeUnique<Timer>([weak = WeakOperation { *this }] {
            if (auto operation = lock(weak); operation && !operation->terminal && !operation->validGeneration())
                operation->finish(RV_RESOURCE_INVALIDATED);
        });
        generationCheck->startRepeating(10_ms);
        image->addClient(*this);
    }

    void notifyFinished(CachedResource&, const NetworkLoadMetrics&, LoadWillContinueInAnotherProcess) final
    {
        if (terminal || decoding)
            return;
        if (!validGeneration()) {
            finish(RV_RESOURCE_INVALIDATED);
            return;
        }
        if (!image || image->errorOccurred() || !image->image()) {
            finish(RV_RESOURCE_LOAD_FAILED);
            return;
        }
        RefPtr bitmap = dynamicDowncast<BitmapImage>(image->image());
        // Matches ImageLoader::decode (Source/WebCore/loader/ImageLoader.cpp:643-645): a non-bitmap image, such as
        // an SVGImage, has no separate decode stage and succeeds once loading finishes.
        if (!bitmap) {
            finish(RV_RESOURCE_SUCCEEDED);
            return;
        }
        decoding = true;
        bitmap->decode([weak = WeakOperation { *this }](DecodingStatus status) {
            if (auto operation = lock(weak))
                operation->finish(status == DecodingStatus::Invalid ? RV_RESOURCE_DECODE_FAILED : RV_RESOURCE_SUCCEEDED);
        });
    }
};

WTF_MAKE_TZONE_ALLOCATED_IMPL(ImageOperation);

RefPtr<ImageOperation> lock(const WeakOperation& weak)
{
    return static_cast<ImageOperation*>(weak.get());
}

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
