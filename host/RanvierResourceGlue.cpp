#include "config.h"
#include "RanvierResourceGlue.h"
#include "CSSFontFace.h"
#include "CachedImage.h"
#include "Document.h"
#include "DocumentInlines.h"
#include "FontFace.h"
#include "FontFaceSet.h"
#include "HTMLImageElement.h"
#include "HTMLElementTypeHelpers.h"
#include "Image.h"
#include "ImageLoader.h"
#include "Node.h"
#include "SVGImageElement.h"
#include "SVGElementTypeHelpers.h"
#include <JavaScriptCore/ArrayBuffer.h>
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

// One terminal outcome per operation, delivered on the owning thread; see RanvierResourceGlue.h.
class Operation : public RefCounted<Operation>, public CanMakeSingleThreadWeakPtr<Operation> {
    WTF_MAKE_TZONE_ALLOCATED(Operation);

public:
    virtual ~Operation() = default;

    RefPtr<Document> document;
    RvResourceCompletion callback { nullptr };
    void* context { nullptr };
    bool terminal { false };
    bool starting { false };
    bool pending { false };
    int32_t pendingOutcome { 0 };
    int32_t pendingWidth { 0 };
    int32_t pendingHeight { 0 };

    // Engine objects released at a terminal outcome; a held lease (a registered font) survives until release.
    virtual void detach() { document = nullptr; }
    // Releases a lease the operation still holds after its terminal outcome.
    virtual void dispose() { detach(); }
    virtual void measure(int32_t&, int32_t&) { }

    void finish(int32_t outcome)
    {
        if (terminal)
            return;
        Ref protectThis { *this };
        terminal = true;
        int32_t width = 0;
        int32_t height = 0;
        if (outcome == RV_RESOURCE_SUCCEEDED)
            measure(width, height);
        if (outcome != RV_RESOURCE_SUCCEEDED)
            dispose();
        else
            detach();
        pending = true;
        pendingOutcome = outcome;
        pendingWidth = width;
        pendingHeight = height;
        if (!starting) {
            flush();
            return;
        }
        // A terminal reached inside the starting call is delivered on a later run-loop turn.
        RunLoop::mainSingleton().dispatch([weak = SingleThreadWeakPtr<Operation> { *this }] {
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

    virtual bool belongsTo(const Document& candidate) const { return document == &candidate; }

protected:
    Operation(Document& document, RvResourceCompletion callback, void* context)
        : document(&document)
        , callback(callback)
        , context(context)
    {
    }
};

WTF_MAKE_TZONE_ALLOCATED_IMPL(Operation);

class ImageOperation final : public Operation {
    WTF_MAKE_TZONE_ALLOCATED(ImageOperation);

public:
    static Ref<ImageOperation> create(Document& document, Element& target, RvResourceCompletion callback, void* context)
    {
        return adoptRef(*new ImageOperation(document, target, callback, context));
    }

    RefPtr<Element> target;

    // A terminal operation holds no engine object. A waiter still queued in the ImageLoader holds only a weak pointer.
    void detach() final
    {
        target = nullptr;
        Operation::detach();
    }

    void measure(int32_t& width, int32_t& height) final
    {
        if (!target)
            return;
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

    void start()
    {
        starting = true;
        // The ImageLoader settles the waiter at the points where it settles decode() promises (patch 0033).
        Function<void(ImageDecodeResult)> waiter = [weak = SingleThreadWeakPtr<Operation> { *this }](ImageDecodeResult result) {
            if (RefPtr operation = weak.get())
                operation->finish(outcomeFor(result));
        };
        if (auto* element = dynamicDowncast<HTMLImageElement>(*target))
            element->decode(WTF::move(waiter));
        else
            downcast<SVGImageElement>(*target).decode(WTF::move(waiter));
        starting = false;
    }

private:
    ImageOperation(Document& document, Element& target, RvResourceCompletion callback, void* context)
        : Operation(document, callback, context)
        , target(&target)
    {
    }
};

WTF_MAKE_TZONE_ALLOCATED_IMPL(ImageOperation);

// Owns a FontFace built from caller bytes. The face joins the document's FontFaceSet only after CSSFontFace reports
// Success, and leaves it when the operation is released or its document is invalidated.
class FontOperation final : public Operation, public CSSFontFaceClient {
    WTF_MAKE_TZONE_ALLOCATED(FontOperation);

public:
    static Ref<FontOperation> create(Document& document, RvResourceCompletion callback, void* context)
    {
        return adoptRef(*new FontOperation(document, callback, context));
    }

    void ref() const final { Operation::ref(); }
    void deref() const final { Operation::deref(); }

    RefPtr<FontFace> face;
    RefPtr<Document> lease;
    bool registered { false };
    bool observing { false };

    void stopObserving()
    {
        if (observing && face)
            face->backing().removeClient(*this);
        observing = false;
    }

    // Success keeps the registered face and its document as a lease until release.
    void detach() final
    {
        stopObserving();
        if (!registered)
            face = nullptr;
        Operation::detach();
    }

    void dispose() final
    {
        stopObserving();
        if (registered && face && lease)
            lease->fonts()->remove(*face);
        registered = false;
        face = nullptr;
        lease = nullptr;
        Operation::detach();
    }

    bool belongsTo(const Document& candidate) const final { return document == &candidate || lease == &candidate; }

    void settle(CSSFontFace::Status status)
    {
        switch (status) {
        case CSSFontFace::Status::Success: {
            if (!document || !face) {
                finish(RV_RESOURCE_INVALIDATED);
                return;
            }
            auto added = document->fonts()->add(*face);
            if (added.hasException()) {
                finish(RV_RESOURCE_LOAD_FAILED);
                return;
            }
            registered = true;
            lease = document;
            finish(RV_RESOURCE_SUCCEEDED);
            return;
        }
        case CSSFontFace::Status::Failure:
            finish(RV_RESOURCE_DECODE_FAILED);
            return;
        case CSSFontFace::Status::TimedOut:
            finish(RV_RESOURCE_LOAD_FAILED);
            return;
        case CSSFontFace::Status::Pending:
        case CSSFontFace::Status::Loading:
            return;
        }
    }

    void fontStateChanged(CSSFontFace&, CSSFontFace::Status, CSSFontFace::Status newState) final
    {
        if (!terminal)
            settle(newState);
    }

    void start(const String& family, std::span<const uint8_t> bytes)
    {
        starting = true;
        RefPtr buffer = JSC::ArrayBuffer::tryCreate(bytes);
        if (!buffer) {
            finish(RV_RESOURCE_LOAD_FAILED);
            starting = false;
            return;
        }
        face = FontFace::create(*document, AtomString { family }, FontFace::Source { buffer.releaseNonNull() }, FontFace::Descriptors { });
        face->backing().addClient(*this);
        observing = true;
        auto status = face->backing().status();
        if (status == CSSFontFace::Status::Pending) {
            face->backing().load();
            status = face->backing().status();
        }
        if (!terminal)
            settle(status);
        starting = false;
    }

private:
    FontOperation(Document& document, RvResourceCompletion callback, void* context)
        : Operation(document, callback, context)
    {
    }
};

WTF_MAKE_TZONE_ALLOCATED_IMPL(FontOperation);

std::unordered_map<uint64_t, Ref<Operation>>& operations()
{
    static NeverDestroyed<std::unordered_map<uint64_t, Ref<Operation>>> values;
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
    value->dispose();
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
    Ref value = ImageOperation::create(*document, *target, callback, context);
    *operation = nextOperation++;
    operations().emplace(*operation, value.copyRef());
    value->start();
    return RV_OK;
}

int32_t ranvier_resource_load_font(RvNode* documentHandle, const char* family, const uint8_t* bytes, int32_t length, RvResourceCompletion callback, void* context, uint64_t* operation)
{
    if (!documentHandle || !family || (!bytes && length) || length < 0 || !callback || !operation)
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    auto* document = documentFromHandle(documentHandle);
    auto name = String::fromUTF8(family);
    if (!document || !document->window() || name.isNull() || name.isEmpty() || !nextOperation)
        return RV_ERR_UNSUPPORTED;
    Ref value = FontOperation::create(*document, callback, context);
    *operation = nextOperation++;
    operations().emplace(*operation, value.copyRef());
    value->start(name, std::span<const uint8_t> { bytes, static_cast<size_t>(length) });
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
    Vector<uint64_t> affected;
    for (auto& entry : operations()) {
        if (entry.second->belongsTo(*document))
            affected.append(entry.first);
    }
    for (auto operation : affected) {
        auto found = operations().find(operation);
        Ref value = found->second;
        if (value->terminal) {
            // A delivered outcome stays registered until release; only its lease ends with the document.
            value->dispose();
            continue;
        }
        releaseOperation(operation, RV_RESOURCE_INVALIDATED);
    }
}
