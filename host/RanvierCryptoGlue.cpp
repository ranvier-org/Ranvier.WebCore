#include "config.h"
#include "RanvierCryptoGlue.h"
#include "dom/RanvierDomGlue.h"
#include "CryptoAlgorithm.h"
#include "CryptoAlgorithmHmacKeyParams.h"
#include "CryptoAlgorithmParameters.h"
#include "CryptoAlgorithmRegistry.h"
#include "CryptoKeyHMAC.h"
#include "DOMException.h"
#include "Document.h"
#include "Exception.h"
#include "Node.h"
#include "ScriptExecutionContext.h"
#include <wtf/MainThread.h>
#include <wtf/NeverDestroyed.h>
#include <wtf/StdLibExtras.h>
#include <wtf/TZoneMallocInlines.h>
#include <wtf/WorkQueue.h>
#include <wtf/text/CString.h>
#include <limits>
#include <map>
#include <memory>

using namespace WebCore;

namespace {

enum class ResultKind { Key, Bytes, Boolean, Error };

struct Result {
    WTF_MAKE_TZONE_ALLOCATED_INLINE(Result);

public:
    explicit Result(ResultKind kind) : kind(kind) { }
    ~Result() { secureZeroSpan(bytes.mutableSpan()); }
    ResultKind kind;
    RefPtr<CryptoKey> key;
    Vector<uint8_t> bytes;
    bool boolean { false };
    ExceptionCode error { ExceptionCode::OperationError };
};

struct Operation {
    WTF_MAKE_TZONE_ALLOCATED_INLINE(Operation);

public:
    explicit Operation(Document& document) : document(document) { }
    WeakPtr<Document, WeakPtrImplWithEventTargetData> document;
    bool queued { false };
    std::unique_ptr<Result> result;
};

struct KeyEntry {
    RefPtr<CryptoKey> key;
    uint64_t references { 1 };
};

struct State {
    uint64_t nextToken { 1 };
    std::map<uint64_t, std::unique_ptr<Operation>> operations;
    std::map<uint64_t, KeyEntry> keys;
};

State& state()
{
    static NeverDestroyed<State> value;
    return value.get();
}

uint64_t token()
{
    auto& value = state().nextToken;
    RELEASE_ASSERT(value != std::numeric_limits<uint64_t>::max());
    return value++;
}

WorkQueue& queue()
{
    static NeverDestroyed<Ref<WorkQueue>> value(WorkQueue::create("org.ranvier.WebCrypto"_s));
    return value.get().get();
}

bool valid(RanvierCryptoBytes bytes)
{
    return bytes.length >= 0 && (!bytes.length || bytes.data);
}

Vector<uint8_t> copy(RanvierCryptoBytes bytes)
{
    return Vector<uint8_t>(std::span { bytes.data, static_cast<size_t>(bytes.length) });
}

String text(RanvierCryptoBytes bytes)
{
    return String::fromUTF8(std::span { reinterpret_cast<const char*>(bytes.data), static_cast<size_t>(bytes.length) });
}

int32_t documentOf(RvNode* handle, Document*& document)
{
    if (!isMainThread())
        return RV_ERR_WRONG_THREAD;
    if (!handle)
        return RV_ERR_NULL_ARGUMENT;
    document = dynamicDowncast<Document>(reinterpret_cast<Node*>(handle));
    if (!document)
        return RV_ERR_WRONG_INTERFACE;
    if (!document->isFullyActive() || document->activeDOMObjectsAreStopped())
        return RV_ERR_DETACHED;
    return RV_OK;
}

std::unique_ptr<Result> errorResult(ExceptionCode error)
{
    auto result = makeUnique<Result>(ResultKind::Error);
    result->error = error;
    return result;
}

Operation* operation(uint64_t id)
{
    auto found = state().operations.find(id);
    if (found == state().operations.end())
        return nullptr;
    auto& value = *found->second;
    if (!value.result && (!value.document || value.document->activeDOMObjectsAreStopped() || !value.document->isFullyActive()))
        value.result = errorResult(ExceptionCode::AbortError);
    return &value;
}

void deliver(uint64_t id, std::unique_ptr<Result>&& result)
{
    auto* value = operation(id);
    if (!value || value->result || value->queued)
        return;
    value->queued = true;
    value->document->postTask([id, result = WTF::move(result)](ScriptExecutionContext&) mutable {
        auto* value = operation(id);
        if (value && !value->result)
            value->result = WTF::move(result);
    });
}

auto onError(uint64_t id)
{
    return [id](ExceptionCode error) { deliver(id, errorResult(error)); };
}

void deliverKey(uint64_t id, CryptoKey& key)
{
    if (!key.usagesBitmap()) {
        deliver(id, errorResult(ExceptionCode::SyntaxError));
        return;
    }
    auto result = makeUnique<Result>(ResultKind::Key);
    result->key = &key;
    deliver(id, WTF::move(result));
}

uint64_t admit(Document& document, RanvierCryptoOperationHandle* output)
{
    auto id = token();
    state().operations.emplace(id, makeUnique<Operation>(document));
    output->value = id;
    return id;
}

int32_t checkParams(const RanvierCryptoHmacParams* params)
{
    if (!params || params->size != sizeof(*params) || !valid(params->hash)
        || params->usages.count < 0 || (params->usages.count && !params->usages.items)
        || (params->extractable != 0 && params->extractable != 1)
        || (params->length_present != 0 && params->length_present != 1))
        return RV_ERR_NULL_ARGUMENT;
    for (int32_t index = 0; index < params->usages.count; ++index) {
        if (!valid(params->usages.items[index]))
            return RV_ERR_NULL_ARGUMENT;
    }
    return RV_OK;
}

std::optional<ExceptionCode> normalize(const RanvierCryptoHmacParams& input, CryptoAlgorithmHmacKeyParams& params, CryptoKeyUsageBitmap& usages)
{
    usages = 0;
    for (int32_t index = 0; index < input.usages.count; ++index) {
        auto usage = text(input.usages.items[index]);
        if (usage == "sign"_s)
            usages |= CryptoKeyUsageSign;
        else if (usage == "verify"_s)
            usages |= CryptoKeyUsageVerify;
        else if (usage == "encrypt"_s)
            usages |= CryptoKeyUsageEncrypt;
        else if (usage == "decrypt"_s)
            usages |= CryptoKeyUsageDecrypt;
        else if (usage == "deriveKey"_s)
            usages |= CryptoKeyUsageDeriveKey;
        else if (usage == "deriveBits"_s)
            usages |= CryptoKeyUsageDeriveBits;
        else if (usage == "wrapKey"_s)
            usages |= CryptoKeyUsageWrapKey;
        else if (usage == "unwrapKey"_s)
            usages |= CryptoKeyUsageUnwrapKey;
        else
            return ExceptionCode::TypeError;
    }
    auto hash = CryptoAlgorithmRegistry::singleton().identifier(text(input.hash));
    if (!hash || (*hash != CryptoAlgorithmIdentifier::SHA_1 && *hash != CryptoAlgorithmIdentifier::SHA_256
        && *hash != CryptoAlgorithmIdentifier::SHA_384 && *hash != CryptoAlgorithmIdentifier::SHA_512))
        return ExceptionCode::NotSupportedError;
    params.hashIdentifier = *hash;
    params.hash = CryptoAlgorithmRegistry::singleton().name(*hash);
    if (input.length_present)
        params.length = input.length_bits;
    return std::nullopt;
}

int32_t lookupKey(RanvierCryptoKeyHandle handle, RefPtr<CryptoKey>& key)
{
    if (!isMainThread())
        return RV_ERR_WRONG_THREAD;
    auto found = state().keys.find(handle.value);
    if (found == state().keys.end())
        return state().operations.contains(handle.value) ? int32_t { RV_ERR_WRONG_INTERFACE } : int32_t { RV_ERR_DETACHED };
    key = found->second.key;
    return RV_OK;
}

int32_t lookupOperation(RanvierCryptoOperationHandle handle, Operation*& value)
{
    if (!isMainThread())
        return RV_ERR_WRONG_THREAD;
    value = operation(handle.value);
    if (!value)
        return state().keys.contains(handle.value) ? int32_t { RV_ERR_WRONG_INTERFACE } : int32_t { RV_ERR_DETACHED };
    return RV_OK;
}

int32_t resultOf(RanvierCryptoOperationHandle handle, ResultKind kind, Result*& result)
{
    Operation* value;
    if (auto status = lookupOperation(handle, value))
        return status;
    if (!value->result)
        return RV_ERR_UNSUPPORTED;
    result = value->result.get();
    if (result->kind == ResultKind::Error)
        return Ranvier::recordException(Exception { result->error });
    return result->kind == kind ? RV_OK : RV_ERR_WRONG_INTERFACE;
}

int32_t copyBytes(std::span<const uint8_t> bytes, uint8_t* buffer, int32_t capacity, int32_t* length)
{
    if (!length || capacity < 0 || (capacity && !buffer))
        return RV_ERR_NULL_ARGUMENT;
    if (bytes.size() > INT32_MAX)
        return RV_ERR_BUFFER_TOO_SMALL;
    *length = static_cast<int32_t>(bytes.size());
    if (static_cast<size_t>(capacity) < bytes.size())
        return RV_ERR_BUFFER_TOO_SMALL;
    if (!bytes.empty())
        memcpy(buffer, bytes.data(), bytes.size());
    return RV_OK;
}

int32_t startKey(RvNode* handle, const RanvierCryptoHmacParams* input, const RanvierCryptoBytes* raw, RanvierCryptoOperationHandle* output)
{
    Document* document;
    if (auto status = documentOf(handle, document))
        return status;
    if (!output)
        return RV_ERR_NULL_ARGUMENT;
    output->value = 0;
    if (auto status = checkParams(input))
        return status;
    if (raw && !valid(*raw))
        return RV_ERR_NULL_ARGUMENT;
    auto id = admit(*document, output);
    CryptoAlgorithmHmacKeyParams params(CryptoAlgorithmIdentifier::HMAC);
    CryptoKeyUsageBitmap usages;
    if (auto error = normalize(*input, params, usages)) {
        deliver(id, errorResult(*error));
        return RV_OK;
    }
    if (raw && input->length_present && !input->length_bits) {
        deliver(id, errorResult(ExceptionCode::DataError));
        return RV_OK;
    }
    auto algorithm = CryptoAlgorithmRegistry::singleton().create(CryptoAlgorithmIdentifier::HMAC);
    if (!algorithm) {
        deliver(id, errorResult(ExceptionCode::NotSupportedError));
        return RV_OK;
    }
    if (raw) {
        algorithm->importKey(CryptoKeyFormat::Raw, KeyData { copy(*raw) }, params, input->extractable, usages,
            [id](CryptoKey& key) { deliverKey(id, key); }, onError(id));
    } else {
        algorithm->generateKey(params, input->extractable, usages, [id](KeyOrKeyPair&& result) {
            if (auto* key = std::get_if<Ref<CryptoKey>>(&result))
                deliverKey(id, key->get());
            else
                deliver(id, errorResult(ExceptionCode::OperationError));
        }, onError(id), *document);
    }
    return RV_OK;
}

int32_t startData(RvNode* handle, RanvierCryptoKeyHandle keyHandle, RanvierCryptoBytes data, const RanvierCryptoBytes* signature, RanvierCryptoOperationHandle* output)
{
    Document* document;
    if (auto status = documentOf(handle, document))
        return status;
    if (!output)
        return RV_ERR_NULL_ARGUMENT;
    output->value = 0;
    if (!valid(data) || (signature && !valid(*signature)))
        return RV_ERR_NULL_ARGUMENT;
    RefPtr<CryptoKey> key;
    if (auto status = lookupKey(keyHandle, key))
        return status;
    auto id = admit(*document, output);
    if (key->algorithmIdentifier() != CryptoAlgorithmIdentifier::HMAC
        || !key->allows(signature ? CryptoKeyUsageVerify : CryptoKeyUsageSign)) {
        deliver(id, errorResult(ExceptionCode::InvalidAccessError));
        return RV_OK;
    }
    auto algorithm = CryptoAlgorithmRegistry::singleton().create(CryptoAlgorithmIdentifier::HMAC);
    if (!algorithm) {
        deliver(id, errorResult(ExceptionCode::NotSupportedError));
        return RV_OK;
    }
    CryptoAlgorithmParameters params(CryptoAlgorithmIdentifier::HMAC);
    if (signature) {
        algorithm->doVerify(params, key.releaseNonNull(), copy(*signature), copy(data), [id](bool valid) {
            auto result = makeUnique<Result>(ResultKind::Boolean);
            result->boolean = valid;
            deliver(id, WTF::move(result));
        }, onError(id), *document, queue());
    } else {
        algorithm->sign(params, key.releaseNonNull(), copy(data), [id](const Vector<uint8_t>& bytes) {
            auto result = makeUnique<Result>(ResultKind::Bytes);
            result->bytes = bytes;
            deliver(id, WTF::move(result));
        }, onError(id), *document, queue());
    }
    return RV_OK;
}

}

int32_t ranvier_crypto_hmac_supported(RvNode* handle, int32_t* supported)
{
    Document* document;
    if (auto status = documentOf(handle, document))
        return status;
    if (!supported)
        return RV_ERR_NULL_ARGUMENT;
    *supported = !!CryptoAlgorithmRegistry::singleton().create(CryptoAlgorithmIdentifier::HMAC);
    return RV_OK;
}

int32_t ranvier_crypto_hmac_generate(RvNode* document, const RanvierCryptoHmacParams* params, RanvierCryptoOperationHandle* output)
{
    return startKey(document, params, nullptr, output);
}

int32_t ranvier_crypto_hmac_import_raw(RvNode* document, const RanvierCryptoHmacParams* params, RanvierCryptoBytes raw, RanvierCryptoOperationHandle* output)
{
    return startKey(document, params, &raw, output);
}

int32_t ranvier_crypto_hmac_sign(RvNode* document, RanvierCryptoKeyHandle key, RanvierCryptoBytes data, RanvierCryptoOperationHandle* output)
{
    return startData(document, key, data, nullptr, output);
}

int32_t ranvier_crypto_hmac_verify(RvNode* document, RanvierCryptoKeyHandle key, RanvierCryptoBytes signature, RanvierCryptoBytes data, RanvierCryptoOperationHandle* output)
{
    return startData(document, key, data, &signature, output);
}

int32_t ranvier_crypto_hmac_export_raw(RvNode* handle, RanvierCryptoKeyHandle keyHandle, RanvierCryptoOperationHandle* output)
{
    Document* document;
    if (auto status = documentOf(handle, document))
        return status;
    if (!output)
        return RV_ERR_NULL_ARGUMENT;
    output->value = 0;
    RefPtr<CryptoKey> key;
    if (auto status = lookupKey(keyHandle, key))
        return status;
    auto id = admit(*document, output);
    if (!key->extractable()) {
        deliver(id, errorResult(ExceptionCode::InvalidAccessError));
        return RV_OK;
    }
    if (key->algorithmIdentifier() != CryptoAlgorithmIdentifier::HMAC) {
        deliver(id, errorResult(ExceptionCode::InvalidAccessError));
        return RV_OK;
    }
    auto algorithm = CryptoAlgorithmRegistry::singleton().create(CryptoAlgorithmIdentifier::HMAC);
    if (!algorithm) {
        deliver(id, errorResult(ExceptionCode::NotSupportedError));
        return RV_OK;
    }
    algorithm->exportKey(CryptoKeyFormat::Raw, key.releaseNonNull(), [id](CryptoKeyFormat, KeyData&& data) {
        auto result = makeUnique<Result>(ResultKind::Bytes);
        if (auto* bytes = std::get_if<Vector<uint8_t>>(&data)) {
            result->bytes = WTF::move(*bytes);
            deliver(id, WTF::move(result));
        } else
            deliver(id, errorResult(ExceptionCode::OperationError));
    }, onError(id));
    return RV_OK;
}

int32_t ranvier_crypto_operation_ready(RanvierCryptoOperationHandle handle, int32_t* ready)
{
    Operation* value;
    if (auto status = lookupOperation(handle, value))
        return status;
    if (!ready)
        return RV_ERR_NULL_ARGUMENT;
    *ready = !!value->result;
    return RV_OK;
}

int32_t ranvier_crypto_operation_error(RanvierCryptoOperationHandle handle, char* buffer, int32_t capacity, int32_t* length)
{
    Operation* value;
    if (auto status = lookupOperation(handle, value))
        return status;
    if (!value->result)
        return RV_ERR_UNSUPPORTED;
    auto name = value->result->kind == ResultKind::Error
        ? String(value->result->error == ExceptionCode::TypeError ? "TypeError"_s : DOMException::name(value->result->error)).utf8()
        : CString("");
    return copyBytes(std::span { reinterpret_cast<const uint8_t*>(name.data()), name.length() }, reinterpret_cast<uint8_t*>(buffer), capacity, length);
}

int32_t ranvier_crypto_operation_take_key(RanvierCryptoOperationHandle handle, RanvierCryptoKeyHandle* key)
{
    if (!isMainThread())
        return RV_ERR_WRONG_THREAD;
    if (!key)
        return RV_ERR_NULL_ARGUMENT;
    key->value = 0;
    Result* result;
    if (auto status = resultOf(handle, ResultKind::Key, result))
        return status;
    if (!result->key)
        return RV_ERR_UNSUPPORTED;
    auto id = token();
    state().keys.emplace(id, KeyEntry { WTF::move(result->key), 1 });
    key->value = id;
    return RV_OK;
}

int32_t ranvier_crypto_operation_bytes(RanvierCryptoOperationHandle handle, uint8_t* buffer, int32_t capacity, int32_t* length)
{
    Result* result;
    if (auto status = resultOf(handle, ResultKind::Bytes, result))
        return status;
    return copyBytes(result->bytes.span(), buffer, capacity, length);
}

int32_t ranvier_crypto_operation_boolean(RanvierCryptoOperationHandle handle, int32_t* boolean)
{
    Result* result;
    if (auto status = resultOf(handle, ResultKind::Boolean, result))
        return status;
    if (!boolean)
        return RV_ERR_NULL_ARGUMENT;
    *boolean = result->boolean;
    return RV_OK;
}

int32_t ranvier_crypto_operation_release(RanvierCryptoOperationHandle handle)
{
    Operation* value;
    if (auto status = lookupOperation(handle, value))
        return status;
    state().operations.erase(handle.value);
    return RV_OK;
}

int32_t ranvier_crypto_key_retain(RanvierCryptoKeyHandle handle)
{
    RefPtr<CryptoKey> key;
    if (auto status = lookupKey(handle, key))
        return status;
    auto& references = state().keys.at(handle.value).references;
    if (references == std::numeric_limits<uint64_t>::max())
        return RV_ERR_UNSUPPORTED;
    ++references;
    return RV_OK;
}

int32_t ranvier_crypto_key_release(RanvierCryptoKeyHandle handle)
{
    RefPtr<CryptoKey> key;
    if (auto status = lookupKey(handle, key))
        return status;
    if (!--state().keys.at(handle.value).references)
        state().keys.erase(handle.value);
    return RV_OK;
}

int32_t ranvier_crypto_hmac_key_info(RanvierCryptoKeyHandle handle, RanvierCryptoHmacKeyInfo* info)
{
    RefPtr<CryptoKey> key;
    if (auto status = lookupKey(handle, key))
        return status;
    if (!info || info->size != sizeof(*info))
        return RV_ERR_NULL_ARGUMENT;
    auto* hmac = dynamicDowncast<CryptoKeyHMAC>(*key);
    if (!hmac)
        return RV_ERR_WRONG_INTERFACE;
    auto metadata = key->algorithm();
    auto* algorithm = std::get_if<CryptoHmacKeyAlgorithm>(&metadata);
    if (!algorithm)
        return RV_ERR_WRONG_INTERFACE;
    *info = { sizeof(*info), key->extractable(), algorithm->length,
        key->allows(CryptoKeyUsageSign), key->allows(CryptoKeyUsageVerify) };
    return RV_OK;
}

int32_t ranvier_crypto_hmac_key_hash(RanvierCryptoKeyHandle handle, char* buffer, int32_t capacity, int32_t* length)
{
    RefPtr<CryptoKey> key;
    if (auto status = lookupKey(handle, key))
        return status;
    auto* hmac = dynamicDowncast<CryptoKeyHMAC>(*key);
    if (!hmac)
        return RV_ERR_WRONG_INTERFACE;
    auto name = CryptoAlgorithmRegistry::singleton().name(hmac->hashAlgorithmIdentifier()).utf8();
    return copyBytes(std::span { reinterpret_cast<const uint8_t*>(name.data()), name.length() }, reinterpret_cast<uint8_t*>(buffer), capacity, length);
}
