#include "config.h"
#include "RanvierResourceGlue.h"
#include "Blob.h"
#include "CSSFontFace.h"
#include "CachedImage.h"
#include "DOMException.h"
#include "Document.h"
#include "DocumentInlines.h"
#include "File.h"
#include "FileReader.h"
#include "FileReaderLoader.h"
#include "FileReaderLoaderClient.h"
#include "FontFace.h"
#include "FontFaceSet.h"
#include "HTMLImageElement.h"
#include "HTMLElementTypeHelpers.h"
#include "Image.h"
#include "ImageLoader.h"
#include "Node.h"
#include "OriginAccessPatterns.h"
#include "SVGImageElement.h"
#include "SecurityOrigin.h"
#include "ThreadableBlobRegistry.h"
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

class BlobReadOperation;

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
    virtual BlobReadOperation* asBlobRead() { return nullptr; }

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

// Reads a blob, or the blob a blob URL refers to, through the engine's FileReaderLoader, as Blob.text(),
// arrayBuffer() and bytes() read it. The bytes, the type and the error name stay until release.
class BlobReadOperation final : public Operation, public FileReaderLoaderClient {
    WTF_MAKE_TZONE_ALLOCATED(BlobReadOperation);

public:
    static Ref<BlobReadOperation> create(Document& document, bool text, RvResourceCompletion callback, void* context)
    {
        return adoptRef(*new BlobReadOperation(document, text, callback, context));
    }

    void ref() const final { Operation::ref(); }
    void deref() const final { Operation::deref(); }

    bool text { false };
    bool succeeded { false };
    RefPtr<FileReaderLoader> loader;
    Vector<uint8_t> bytes;
    CString type;
    CString errorName;

    // Cancels a load in flight. A loader reaching its terminal calls its client last, so the reference ends on a
    // later run-loop turn.
    void detach() final
    {
        if (RefPtr current = std::exchange(loader, nullptr)) {
            current->cancel();
            RunLoop::mainSingleton().dispatch([current = WTF::move(current)] { });
        }
        Operation::detach();
    }

    BlobReadOperation* asBlobRead() final { return this; }

    // A URL the document cannot request fails as an unknown one does.
    void deny()
    {
        starting = true;
        didFail(ExceptionCode::NotFoundError);
        starting = false;
    }

    void start(Blob* blob, const URL& url)
    {
        starting = true;
        Ref current = FileReaderLoader::create(text ? FileReaderLoader::ReadAsText : FileReaderLoader::ReadAsArrayBuffer, this);
        loader = current.copyRef();
        if (text)
            current->setEncoding("UTF-8"_s);
        if (blob)
            current->start(document.get(), *blob);
        else
            current->start(document.get(), url);
        starting = false;
    }

private:
    BlobReadOperation(Document& document, bool text, RvResourceCompletion callback, void* context)
        : Operation(document, callback, context)
        , text(text)
    {
    }

    void didStartLoading() final { }
    void didReceiveData() final { }

    void didFinishLoading() final
    {
        RefPtr current = loader;
        if (terminal || !current)
            return;
        if (text)
            bytes.append(current->stringResult().utf8(StrictConversionReplacingUnpairedSurrogatesWithFFFD).span());
        else if (RefPtr buffer = current->arrayBufferResult())
            bytes.append(buffer->span());
        succeeded = true;
        finish(RV_RESOURCE_SUCCEEDED);
    }

    void didFail(ExceptionCode code) final
    {
        if (terminal)
            return;
        errorName = String { DOMException::name(code) }.utf8();
        finish(RV_RESOURCE_LOAD_FAILED);
    }
};

WTF_MAKE_TZONE_ALLOCATED_IMPL(BlobReadOperation);

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

namespace {

int32_t startBlobRead(Document& document, Blob* blob, const URL& url, bool text, RvResourceCompletion callback, void* context, uint64_t* operation, bool denied = false)
{
    if (!nextOperation)
        return RV_ERR_UNSUPPORTED;
    Ref value = BlobReadOperation::create(document, text, callback, context);
    *operation = nextOperation++;
    operations().emplace(*operation, value.copyRef());
    if (denied) {
        value->deny();
        return RV_OK;
    }
    value->type = (blob ? blob->type() : ThreadableBlobRegistry::blobType(url)).utf8();
    value->start(blob, url);
    return RV_OK;
}

BlobReadOperation* blobRead(uint64_t operation)
{
    auto found = operations().find(operation);
    return found == operations().end() ? nullptr : found->second->asBlobRead();
}

int32_t copyText(std::span<const char> text, char* buffer, int32_t capacity, int32_t* length)
{
    if (!length || capacity < 0 || (capacity && !buffer))
        return RV_ERR_NULL_ARGUMENT;
    if (text.size() >= static_cast<size_t>(std::numeric_limits<int32_t>::max()))
        return RV_ERR_UNSUPPORTED;
    *length = static_cast<int32_t>(text.size());
    if (capacity <= *length)
        return RV_ERR_BUFFER_TOO_SMALL;
    if (!text.empty())
        std::memcpy(buffer, text.data(), text.size());
    buffer[text.size()] = 0;
    return RV_OK;
}

int32_t copyBytes(std::span<const uint8_t> bytes, uint8_t* buffer, int64_t capacity, int64_t* length)
{
    if (!length || capacity < 0 || (capacity && !buffer))
        return RV_ERR_NULL_ARGUMENT;
    *length = static_cast<int64_t>(bytes.size());
    if (static_cast<uint64_t>(capacity) < bytes.size())
        return RV_ERR_BUFFER_TOO_SMALL;
    if (!bytes.empty())
        std::memcpy(buffer, bytes.data(), bytes.size());
    return RV_OK;
}

}

int32_t ranvier_blob_read(RvNode* documentHandle, RvBlob* blobHandle, int32_t mode, RvResourceCompletion callback, void* context, uint64_t* operation)
{
    if (!documentHandle || !blobHandle || !callback || !operation)
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    auto* document = documentFromHandle(documentHandle);
    if (!document || !document->window() || (mode != RV_BLOB_READ_TEXT && mode != RV_BLOB_READ_BYTES))
        return RV_ERR_UNSUPPORTED;
    Ref blob = *reinterpret_cast<Blob*>(blobHandle);
    return startBlobRead(*document, blob.ptr(), { }, mode == RV_BLOB_READ_TEXT, callback, context, operation);
}

int32_t ranvier_blob_url_read(RvNode* documentHandle, const uint8_t* url, int32_t url_length, RvResourceCompletion callback, void* context, uint64_t* operation)
{
    if (!documentHandle || url_length < 0 || (url_length && !url) || !callback || !operation)
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    auto* document = documentFromHandle(documentHandle);
    if (!document || !document->window())
        return RV_ERR_UNSUPPORTED;
    auto text = String::fromUTF8(std::span<const char8_t> { reinterpret_cast<const char8_t*>(url), static_cast<size_t>(url_length) });
    if (text.isNull())
        return RV_ERR_NULL_ARGUMENT;
    URL parsed { text };
    if (!parsed.isValid() || !parsed.protocolIsBlob())
        return RV_ERR_UNSUPPORTED;
    parsed.removeFragmentIdentifier();
    // The blob registry is process-wide; a URL of another origin, such as another host's opaque document, reads as
    // unknown, as an <img> load of it fails.
    bool denied = !document->securityOrigin().canRequest(parsed, OriginAccessPatternsForWebProcess::singleton());
    return startBlobRead(*document, nullptr, parsed, false, callback, context, operation, denied);
}

int32_t ranvier_blob_read_result(uint64_t operation, uint8_t* buffer, int64_t capacity, int64_t* length)
{
    if (!length || capacity < 0 || (capacity && !buffer))
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    auto* read = blobRead(operation);
    if (!read || !read->succeeded)
        return RV_ERR_UNSUPPORTED;
    return copyBytes(read->bytes.span(), buffer, capacity, length);
}

int32_t ranvier_blob_read_type(uint64_t operation, char* buffer, int32_t capacity, int32_t* length)
{
    if (!length || capacity < 0 || (capacity && !buffer))
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    auto* read = blobRead(operation);
    if (!read || !read->succeeded)
        return RV_ERR_UNSUPPORTED;
    return copyText(read->type.span(), buffer, capacity, length);
}

int32_t ranvier_blob_read_error(uint64_t operation, char* buffer, int32_t capacity, int32_t* length)
{
    if (!length || capacity < 0 || (capacity && !buffer))
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    auto* read = blobRead(operation);
    if (!read || read->errorName.isNull())
        return RV_ERR_UNSUPPORTED;
    return copyText(read->errorName.span(), buffer, capacity, length);
}

int32_t ranvier_file_reader_result(RvEventTarget* target, int32_t* kind, uint8_t* buffer, int64_t capacity, int64_t* length)
{
    if (!target || !kind || !length || capacity < 0 || (capacity && !buffer))
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr reader = dynamicDowncast<FileReader>(*reinterpret_cast<EventTarget*>(target));
    if (!reader)
        return RV_ERR_WRONG_INTERFACE;
    auto result = reader->result();
    if (!result) {
        *kind = RV_FILE_READER_RESULT_NULL;
        *length = 0;
        return RV_OK;
    }
    return WTF::switchOn(*result, [&](const String& text) {
        *kind = RV_FILE_READER_RESULT_STRING;
        auto utf8 = text.utf8(StrictConversionReplacingUnpairedSurrogatesWithFFFD);
        return copyBytes(byteCast<uint8_t>(utf8.span()), buffer, capacity, length);
    }, [&](const Ref<JSC::ArrayBuffer>& bytes) {
        *kind = RV_FILE_READER_RESULT_BYTES;
        return copyBytes(bytes->span(), buffer, capacity, length);
    });
}

int32_t ranvier_file_reader_error(RvEventTarget* target, char* buffer, int32_t capacity, int32_t* length)
{
    if (!target || !length || capacity < 0 || (capacity && !buffer))
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    RefPtr reader = dynamicDowncast<FileReader>(*reinterpret_cast<EventTarget*>(target));
    if (!reader)
        return RV_ERR_WRONG_INTERFACE;
    RefPtr error = reader->error();
    if (!error) {
        *length = -1;
        return RV_OK;
    }
    return copyText(error->name().utf8().span(), buffer, capacity, length);
}
