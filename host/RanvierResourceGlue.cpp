#include "config.h"
#include "RanvierResourceGlue.h"
#include "Blob.h"
#include "CSSFontFace.h"
#include "CSSStyleImageValue.h"
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
#include "HTMLCanvasElement.h"
#include "HTMLImageElement.h"
#include "ImageBitmap.h"
#include "ImageBitmapOptions.h"
#include "ImageData.h"
#include "HTMLElementTypeHelpers.h"
#include "Image.h"
#include "ImageLoader.h"
#include "MediaCapabilitiesNativeQuery.h"
#include "MediaDecodingConfiguration.h"
#include "MediaEncodingConfiguration.h"
#include "Node.h"
#include "OriginAccessPatterns.h"
#include "PlatformMediaEngineConfigurationFactory.h"
#include "SVGImageElement.h"
#include "SecurityOrigin.h"
#include "ThreadableBlobRegistry.h"
#include "SVGElementTypeHelpers.h"
#include "dom/RanvierDomGlue.h"
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
class MediaQueryOperation;
class ImageBitmapOperation;

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
    virtual MediaQueryOperation* asMediaQuery() { return nullptr; }
    virtual ImageBitmapOperation* asImageBitmap() { return nullptr; }

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

// MediaCapabilities.decodingInfo() or encodingInfo() through patch 0043. The providers can answer inside the starting
// call, where finish() defers delivery to a later run-loop turn.
class MediaQueryOperation final : public Operation {
    WTF_MAKE_TZONE_ALLOCATED(MediaQueryOperation);

public:
    static Ref<MediaQueryOperation> create(Document& document, RvResourceCompletion callback, void* context)
    {
        return adoptRef(*new MediaQueryOperation(document, callback, context));
    }

    bool succeeded { false };
    bool rejected { false };
    PlatformMediaCapabilitiesInfo info;

    MediaQueryOperation* asMediaQuery() final { return this; }

    template<typename Result> Function<void(ExceptionOr<Result>&&)> completion()
    {
        return [weak = SingleThreadWeakPtr<Operation> { *this }](ExceptionOr<Result>&& result) {
            RefPtr operation = weak.get();
            if (!operation || operation->terminal)
                return;
            auto& query = *operation->asMediaQuery();
            if (result.hasException()) {
                // A rejected configuration is never registered and never delivered.
                query.rejected = true;
                query.terminal = true;
                query.callback = nullptr;
                return;
            }
            auto value = result.releaseReturnValue();
            query.info = { value.supported, value.smooth, value.powerEfficient };
            query.succeeded = true;
            query.finish(RV_RESOURCE_SUCCEEDED);
        };
    }

private:
    MediaQueryOperation(Document& document, RvResourceCompletion callback, void* context)
        : Operation(document, callback, context)
    {
    }
};

WTF_MAKE_TZONE_ALLOCATED_IMPL(MediaQueryOperation);

// The name rv_last_exception reports for code: the WebIDL error names, else the DOMException name.
CString errorNameFor(ExceptionCode code)
{
    switch (code) {
    case ExceptionCode::RangeError:
        return CString { "RangeError" };
    case ExceptionCode::TypeError:
        return CString { "TypeError" };
    case ExceptionCode::JSSyntaxError:
        return CString { "SyntaxError" };
    default:
        return String { DOMException::name(code) }.utf8();
    }
}

// createImageBitmap through ImageBitmap::createCompletionHandler (patch 0049 for a crop). A source that completes
// inside the starting call is delivered on a later run-loop turn by finish().
class ImageBitmapOperation final : public Operation {
    WTF_MAKE_TZONE_ALLOCATED(ImageBitmapOperation);

public:
    static Ref<ImageBitmapOperation> create(Document& document, RvResourceCompletion callback, void* context)
    {
        return adoptRef(*new ImageBitmapOperation(document, callback, context));
    }

    RefPtr<ImageBitmap> bitmap;
    CString errorName;

    ImageBitmapOperation* asImageBitmap() final { return this; }

    void measure(int32_t& width, int32_t& height) final
    {
        width = bitmap ? static_cast<int32_t>(bitmap->width()) : 0;
        height = bitmap ? static_cast<int32_t>(bitmap->height()) : 0;
    }

    void dispose() final
    {
        bitmap = nullptr;
        detach();
    }

    ImageBitmap::ImageBitmapCompletionHandler completion()
    {
        return [weak = SingleThreadWeakPtr<Operation> { *this }](ExceptionOr<Ref<ImageBitmap>>&& result) {
            RefPtr operation = weak.get();
            if (!operation || operation->terminal)
                return;
            auto& creation = *operation->asImageBitmap();
            if (result.hasException()) {
                creation.errorName = errorNameFor(result.exception().code());
                creation.finish(RV_RESOURCE_DECODE_FAILED);
                return;
            }
            creation.bitmap = result.releaseReturnValue();
            creation.finish(RV_RESOURCE_SUCCEEDED);
        };
    }

private:
    ImageBitmapOperation(Document& document, RvResourceCompletion callback, void* context)
        : Operation(document, callback, context)
    {
    }
};

WTF_MAKE_TZONE_ALLOCATED_IMPL(ImageBitmapOperation);

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

namespace {

std::optional<String> mediaText(const uint8_t* bytes, int32_t length)
{
    if (length < 0 || (length && !bytes))
        return std::nullopt;
    if (!length)
        return emptyString();
    auto text = String::fromUTF8(std::span<const char8_t> { reinterpret_cast<const char8_t*>(bytes), static_cast<size_t>(length) });
    if (text.isNull())
        return std::nullopt;
    return text;
}

template<typename Enum> bool mediaEnum(int32_t value, int32_t count, std::optional<Enum>& result)
{
    if (value == -1)
        return true;
    if (value < 0 || value >= count)
        return false;
    result = static_cast<Enum>(value);
    return true;
}

bool mediaFlag(int32_t value, std::optional<bool>& result)
{
    if (value == -1)
        return true;
    if (value != 0 && value != 1)
        return false;
    result = value == 1;
    return true;
}

bool mediaConfiguration(const RvMediaVideoConfiguration* video, const RvMediaAudioConfiguration* audio, MediaConfiguration& result)
{
    if (video) {
        if (video->size != static_cast<int32_t>(sizeof(RvMediaVideoConfiguration)))
            return false;
        auto contentType = mediaText(video->content_type, video->content_type_length);
        if (!contentType)
            return false;
        VideoConfiguration value;
        value.contentType = *contentType;
        value.width = video->width;
        value.height = video->height;
        value.bitrate = video->bitrate;
        value.framerate = video->framerate;
        if (!mediaFlag(video->alpha_channel, value.alphaChannel)
            || !mediaEnum(video->hdr_metadata_type, 3, value.hdrMetadataType)
            || !mediaEnum(video->color_gamut, 3, value.colorGamut)
            || !mediaEnum(video->transfer_function, 3, value.transferFunction))
            return false;
        result.video = WTF::move(value);
    }
    if (audio) {
        if (audio->size != static_cast<int32_t>(sizeof(RvMediaAudioConfiguration)))
            return false;
        auto contentType = mediaText(audio->content_type, audio->content_type_length);
        if (!contentType)
            return false;
        AudioConfiguration value;
        value.contentType = *contentType;
        if (audio->channels) {
            auto channels = mediaText(audio->channels, audio->channels_length);
            if (!channels)
                return false;
            value.channels = *channels;
        } else if (audio->channels_length)
            return false;
        if (audio->bitrate >= 0)
            value.bitrate = static_cast<uint64_t>(audio->bitrate);
        if (audio->samplerate > static_cast<int64_t>(std::numeric_limits<uint32_t>::max()))
            return false;
        if (audio->samplerate >= 0)
            value.samplerate = static_cast<uint32_t>(audio->samplerate);
        if (!mediaFlag(audio->spatial_rendering, value.spatialRendering))
            return false;
        result.audio = WTF::move(value);
    }
    return true;
}

}

int32_t ranvier_media_capabilities_query(RvNode* documentHandle, int32_t encoding, int32_t type, const RvMediaVideoConfiguration* video,
    const RvMediaAudioConfiguration* audio, RvResourceCompletion callback, void* context, uint64_t* operation)
{
    if (!documentHandle || !callback || !operation)
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    auto* document = documentFromHandle(documentHandle);
    if (!document || !document->window() || !nextOperation)
        return RV_ERR_UNSUPPORTED;
    if (type < 0 || type >= (encoding ? 2 : 3))
        return RV_ERR_UNSUPPORTED;
    MediaConfiguration configuration;
    if (!mediaConfiguration(video, audio, configuration))
        return RV_ERR_UNSUPPORTED;
    Ref value = MediaQueryOperation::create(*document, callback, context);
    value->starting = true;
    if (encoding) {
        MediaEncodingConfiguration query { WTF::move(configuration), static_cast<MediaEncodingType>(type) };
        queryMediaEncodingInfo(*document, WTF::move(query), value->completion<PlatformMediaCapabilitiesEncodingInfo>());
    } else {
        MediaDecodingConfiguration query { WTF::move(configuration), static_cast<MediaDecodingType>(type) };
        queryMediaDecodingInfo(*document, WTF::move(query), value->completion<PlatformMediaCapabilitiesDecodingInfo>());
    }
    value->starting = false;
    if (value->rejected) {
        value->detach();
        return Ranvier::recordException(Exception { ExceptionCode::TypeError });
    }
    *operation = nextOperation++;
    operations().emplace(*operation, WTF::move(value));
    return RV_OK;
}

int32_t ranvier_media_capabilities_info(uint64_t operation, int32_t* supported, int32_t* smooth, int32_t* power_efficient)
{
    if (!supported || !smooth || !power_efficient)
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    auto found = operations().find(operation);
    auto* query = found == operations().end() ? nullptr : found->second->asMediaQuery();
    if (!query || !query->succeeded)
        return RV_ERR_UNSUPPORTED;
    *supported = query->info.supported;
    *smooth = query->info.smooth;
    *power_efficient = query->info.powerEfficient;
    return RV_OK;
}

int32_t ranvier_media_capabilities_provider(int32_t encoding)
{
    if (encoding)
        return PlatformMediaEngineConfigurationFactory::hasEncodingConfigurationFactory() ? 1 : 0;
    return PlatformMediaEngineConfigurationFactory::hasDecodingConfigurationFactory() ? 1 : 0;
}

namespace {

// The engine options for an app request, or nullopt for a value outside its enumeration.
std::optional<ImageBitmapOptions> bitmapOptions(const RvImageBitmapOptions* requested)
{
    ImageBitmapOptions options;
    if (!requested)
        return options;
    if (requested->size < static_cast<int32_t>(sizeof(RvImageBitmapOptions)) || (requested->crop != 0 && requested->crop != 1))
        return std::nullopt;
    if (requested->imageOrientation < 0 || requested->imageOrientation > RV_IMAGE_BITMAP_ORIENTATION_NONE
        || requested->premultiplyAlpha < 0 || requested->premultiplyAlpha > RV_IMAGE_BITMAP_PREMULTIPLY_DEFAULT
        || requested->colorSpaceConversion < 0 || requested->colorSpaceConversion > RV_IMAGE_BITMAP_COLOR_SPACE_CONVERSION_DEFAULT
        || requested->resizeQuality < 0 || requested->resizeQuality > RV_IMAGE_BITMAP_RESIZE_HIGH)
        return std::nullopt;
    options.orientation = static_cast<ImageBitmapOptions::Orientation>(requested->imageOrientation);
    options.premultiplyAlpha = static_cast<ImageBitmapOptions::PremultiplyAlpha>(requested->premultiplyAlpha);
    options.colorSpaceConversion = static_cast<ImageBitmapOptions::ColorSpaceConversion>(requested->colorSpaceConversion);
    options.resizeQuality = static_cast<ImageBitmapOptions::ResizeQuality>(requested->resizeQuality);
    if (requested->resizeWidth)
        options.resizeWidth = requested->resizeWidth;
    if (requested->resizeHeight)
        options.resizeHeight = requested->resizeHeight;
    return options;
}

// The engine source for a handle of kind, or nullopt for a handle of another kind.
std::optional<ImageBitmap::Source> bitmapSource(int32_t kind, void* source)
{
    switch (kind) {
    case RV_IMAGE_BITMAP_SOURCE_NODE: {
        auto& node = *reinterpret_cast<Node*>(source);
        if (RefPtr image = dynamicDowncast<HTMLImageElement>(node))
            return ImageBitmap::Source { image.releaseNonNull() };
        if (RefPtr image = dynamicDowncast<SVGImageElement>(node))
            return ImageBitmap::Source { image.releaseNonNull() };
        if (RefPtr canvas = dynamicDowncast<HTMLCanvasElement>(node))
            return ImageBitmap::Source { canvas.releaseNonNull() };
        return std::nullopt;
    }
    case RV_IMAGE_BITMAP_SOURCE_BITMAP:
        return ImageBitmap::Source { Ref { *reinterpret_cast<ImageBitmap*>(source) } };
    case RV_IMAGE_BITMAP_SOURCE_IMAGE_DATA:
        return ImageBitmap::Source { Ref { *reinterpret_cast<ImageData*>(source) } };
    case RV_IMAGE_BITMAP_SOURCE_BLOB:
        return ImageBitmap::Source { Ref { *reinterpret_cast<Blob*>(source) } };
    default:
        return std::nullopt;
    }
}

ImageBitmapOperation* imageBitmapCreation(uint64_t operation)
{
    auto found = operations().find(operation);
    return found == operations().end() ? nullptr : found->second->asImageBitmap();
}

} // namespace

int32_t ranvier_image_bitmap_create(RvNode* documentHandle, int32_t kind, void* source, const RvImageBitmapOptions* requested,
    RvResourceCompletion callback, void* context, uint64_t* operation)
{
    if (!documentHandle || !source || !callback || !operation)
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    auto* document = documentFromHandle(documentHandle);
    if (!document || !document->window() || !nextOperation)
        return RV_ERR_UNSUPPORTED;
    auto options = bitmapOptions(requested);
    auto engineSource = bitmapSource(kind, source);
    if (!options || !engineSource)
        return RV_ERR_UNSUPPORTED;
    Ref value = ImageBitmapOperation::create(*document, callback, context);
    *operation = nextOperation++;
    operations().emplace(*operation, value.copyRef());
    value->starting = true;
    if (requested && requested->crop)
        ImageBitmap::createCompletionHandler(*document, WTF::move(*engineSource), WTF::move(*options), requested->sx, requested->sy, requested->sw, requested->sh, value->completion());
    else
        ImageBitmap::createCompletionHandler(*document, WTF::move(*engineSource), WTF::move(*options), value->completion());
    value->starting = false;
    return RV_OK;
}

int32_t ranvier_image_bitmap_result(uint64_t operation, RvImageBitmap** bitmap)
{
    if (!bitmap)
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    auto* creation = imageBitmapCreation(operation);
    if (!creation || !creation->bitmap)
        return RV_ERR_UNSUPPORTED;
    *bitmap = reinterpret_cast<RvImageBitmap*>(&Ref { *creation->bitmap }.leakRef());
    return RV_OK;
}

int32_t ranvier_image_bitmap_error(uint64_t operation, char* buffer, int32_t capacity, int32_t* length)
{
    if (!length || capacity < 0 || (capacity && !buffer))
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    auto* creation = imageBitmapCreation(operation);
    if (!creation || creation->errorName.isNull())
        return RV_ERR_UNSUPPORTED;
    return copyText(creation->errorName.span(), buffer, capacity, length);
}
