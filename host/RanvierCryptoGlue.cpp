#include "config.h"
#include "RanvierCryptoGlue.h"
#include "RanvierCryptoAesGlue.h"
#include "dom/RanvierDomGlue.h"
#include "CryptoAlgorithm.h"
#include "CryptoAlgorithmHmacKeyParams.h"
#include "CryptoAlgorithmAesCbcCfbParams.h"
#include "CryptoAlgorithmAesCtrParams.h"
#include "CryptoAlgorithmAesGcmParams.h"
#include "CryptoAlgorithmAesKeyParams.h"
#include "CryptoAlgorithmParameters.h"
#include "CryptoAlgorithmRegistry.h"
#include "CryptoKeyHMAC.h"
#include "CryptoKeyAES.h"
#include "DOMException.h"
#include "Document.h"
#include "Exception.h"
#include "Node.h"
#include "ScriptExecutionContext.h"
#include <wtf/MainThread.h>
#include <wtf/JSONValues.h>
#include <wtf/NeverDestroyed.h>
#include <wtf/StdLibExtras.h>
#include <wtf/TZoneMallocInlines.h>
#include <wtf/WorkQueue.h>
#include <wtf/text/CString.h>
#include <wtf/text/StringBuilder.h>
#include <limits>
#include <map>
#include <memory>

using namespace WebCore;

namespace {

enum class ResultKind { Key, Bytes, Boolean, Error, OctetJwk };

struct OwnedOctetJwk {
    WTF_MAKE_TZONE_ALLOCATED_INLINE(OwnedOctetJwk);

public:
    Vector<uint8_t> kty, k, alg, use;
    Vector<Vector<uint8_t>> usageStrings;
    Vector<RanvierCryptoBytes> usageViews;
    bool ktyPresent { false }, kPresent { false }, algPresent { false }, usePresent { false };
    bool usagesPresent { false }, extPresent { false }, ext { false };

    ~OwnedOctetJwk()
    {
        secureZeroSpan(k.mutableSpan());
    }
};

struct Result {
    WTF_MAKE_TZONE_ALLOCATED_INLINE(Result);

public:
    explicit Result(ResultKind kind) : kind(kind) { }
    ~Result() { secureZeroSpan(bytes.mutableSpan()); }
    ResultKind kind;
    RefPtr<CryptoKey> key;
    Vector<uint8_t> bytes;
    std::unique_ptr<OwnedOctetJwk> jwk;
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

namespace {

bool flag(int32_t value)
{
    return value == 0 || value == 1;
}

bool valid(RanvierCryptoStrings strings)
{
    if (strings.count < 0 || (strings.count && !strings.items))
        return false;
    for (int32_t index = 0; index < strings.count; ++index) {
        if (!valid(strings.items[index]))
            return false;
    }
    return true;
}

std::optional<CryptoKeyUsage> usageOf(const String& name)
{
    if (name == "encrypt"_s) return CryptoKeyUsage::Encrypt;
    if (name == "decrypt"_s) return CryptoKeyUsage::Decrypt;
    if (name == "sign"_s) return CryptoKeyUsage::Sign;
    if (name == "verify"_s) return CryptoKeyUsage::Verify;
    if (name == "deriveKey"_s) return CryptoKeyUsage::DeriveKey;
    if (name == "deriveBits"_s) return CryptoKeyUsage::DeriveBits;
    if (name == "wrapKey"_s) return CryptoKeyUsage::WrapKey;
    if (name == "unwrapKey"_s) return CryptoKeyUsage::UnwrapKey;
    return std::nullopt;
}

String usageName(CryptoKeyUsage usage)
{
    switch (usage) {
    case CryptoKeyUsage::Encrypt: return "encrypt"_s;
    case CryptoKeyUsage::Decrypt: return "decrypt"_s;
    case CryptoKeyUsage::Sign: return "sign"_s;
    case CryptoKeyUsage::Verify: return "verify"_s;
    case CryptoKeyUsage::DeriveKey: return "deriveKey"_s;
    case CryptoKeyUsage::DeriveBits: return "deriveBits"_s;
    case CryptoKeyUsage::WrapKey: return "wrapKey"_s;
    case CryptoKeyUsage::UnwrapKey: return "unwrapKey"_s;
    }
    RELEASE_ASSERT_NOT_REACHED();
}

CryptoKeyUsageBitmap usageBit(CryptoKeyUsage usage)
{
    switch (usage) {
    case CryptoKeyUsage::Encrypt: return CryptoKeyUsageEncrypt;
    case CryptoKeyUsage::Decrypt: return CryptoKeyUsageDecrypt;
    case CryptoKeyUsage::Sign: return CryptoKeyUsageSign;
    case CryptoKeyUsage::Verify: return CryptoKeyUsageVerify;
    case CryptoKeyUsage::DeriveKey: return CryptoKeyUsageDeriveKey;
    case CryptoKeyUsage::DeriveBits: return CryptoKeyUsageDeriveBits;
    case CryptoKeyUsage::WrapKey: return CryptoKeyUsageWrapKey;
    case CryptoKeyUsage::UnwrapKey: return CryptoKeyUsageUnwrapKey;
    }
    RELEASE_ASSERT_NOT_REACHED();
}

std::optional<ExceptionCode> usagesOf(RanvierCryptoStrings strings, CryptoKeyUsageBitmap& usages)
{
    usages = 0;
    for (int32_t index = 0; index < strings.count; ++index) {
        auto usage = usageOf(text(strings.items[index]));
        if (!usage)
            return ExceptionCode::TypeError;
        usages |= usageBit(*usage);
    }
    return std::nullopt;
}

std::optional<CryptoKeyFormat> formatOf(RanvierCryptoBytes value)
{
    auto name = text(value);
    if (name == "raw"_s) return CryptoKeyFormat::Raw;
    if (name == "jwk"_s) return CryptoKeyFormat::Jwk;
    if (name == "spki"_s) return CryptoKeyFormat::Spki;
    if (name == "pkcs8"_s) return CryptoKeyFormat::Pkcs8;
    return std::nullopt;
}

bool isAes(CryptoAlgorithmIdentifier identifier)
{
    return identifier == CryptoAlgorithmIdentifier::AES_CBC || identifier == CryptoAlgorithmIdentifier::AES_CTR
        || identifier == CryptoAlgorithmIdentifier::AES_GCM || identifier == CryptoAlgorithmIdentifier::AES_KW;
}

std::optional<CryptoAlgorithmIdentifier> aesIdentifier(RanvierCryptoBytes name)
{
    auto identifier = CryptoAlgorithmRegistry::singleton().identifier(text(name));
    return identifier && isAes(*identifier) ? identifier : std::nullopt;
}

CryptoKeyUsageBitmap allowedUsages(CryptoAlgorithmIdentifier identifier)
{
    if (identifier == CryptoAlgorithmIdentifier::HMAC)
        return CryptoKeyUsageSign | CryptoKeyUsageVerify;
    if (identifier == CryptoAlgorithmIdentifier::AES_KW)
        return CryptoKeyUsageWrapKey | CryptoKeyUsageUnwrapKey;
    return CryptoKeyUsageEncrypt | CryptoKeyUsageDecrypt | CryptoKeyUsageWrapKey | CryptoKeyUsageUnwrapKey;
}

bool valid(const RanvierCryptoSecretImportParams* input)
{
    if (!input || input->size != sizeof(*input) || !valid(input->name))
        return false;
    if (auto* hmac = input->hmac) {
        if (hmac->size != sizeof(*hmac) || !flag(hmac->hash_present) || !flag(hmac->length_present)
            || (hmac->hash_present && !valid(hmac->hash)))
            return false;
    }
    return true;
}

std::optional<ExceptionCode> importParameters(const RanvierCryptoSecretImportParams& input, std::unique_ptr<CryptoAlgorithmParameters>& params)
{
    auto identifier = CryptoAlgorithmRegistry::singleton().identifier(text(input.name));
    if (!identifier || (!isAes(*identifier) && *identifier != CryptoAlgorithmIdentifier::HMAC))
        return ExceptionCode::NotSupportedError;
    if (*identifier != CryptoAlgorithmIdentifier::HMAC) {
        params = makeUnique<CryptoAlgorithmParameters>(*identifier);
        return std::nullopt;
    }
    if (!input.hmac || !input.hmac->hash_present)
        return ExceptionCode::TypeError;
    auto hash = CryptoAlgorithmRegistry::singleton().identifier(text(input.hmac->hash));
    if (!hash || (*hash != CryptoAlgorithmIdentifier::SHA_1 && *hash != CryptoAlgorithmIdentifier::SHA_256
        && *hash != CryptoAlgorithmIdentifier::SHA_384 && *hash != CryptoAlgorithmIdentifier::SHA_512))
        return ExceptionCode::NotSupportedError;
    auto hmac = makeUnique<CryptoAlgorithmHmacKeyParams>(*identifier);
    hmac->hashIdentifier = *hash;
    hmac->hash = CryptoAlgorithmRegistry::singleton().name(*hash);
    if (input.hmac->length_present)
        hmac->length = input.hmac->length_bits;
    params = WTF::move(hmac);
    return std::nullopt;
}

bool valid(const RanvierCryptoAesCipherParams* input)
{
    if (!input || input->size != sizeof(*input) || !valid(input->name))
        return false;
    if (auto* cbc = input->cbc) {
        if (cbc->size != sizeof(*cbc) || !flag(cbc->iv_present) || (cbc->iv_present && !valid(cbc->iv)))
            return false;
    }
    if (auto* ctr = input->ctr) {
        if (ctr->size != sizeof(*ctr) || !flag(ctr->counter_present) || !flag(ctr->length_present)
            || (ctr->counter_present && !valid(ctr->counter)))
            return false;
    }
    if (auto* gcm = input->gcm) {
        if (gcm->size != sizeof(*gcm) || !flag(gcm->iv_present) || !flag(gcm->additional_data_present) || !flag(gcm->tag_length_present)
            || (gcm->iv_present && !valid(gcm->iv)) || (gcm->additional_data_present && !valid(gcm->additional_data)))
            return false;
    }
    return true;
}

std::span<const uint8_t> bytesOf(RanvierCryptoBytes bytes)
{
    return { bytes.data, static_cast<size_t>(bytes.length) };
}

std::optional<ExceptionCode> cipherParameters(const RanvierCryptoAesCipherParams& input, bool wrapping, std::unique_ptr<CryptoAlgorithmParameters>& params)
{
    auto identifier = aesIdentifier(input.name);
    if (!identifier || (!wrapping && *identifier == CryptoAlgorithmIdentifier::AES_KW))
        return ExceptionCode::NotSupportedError;
    switch (*identifier) {
    case CryptoAlgorithmIdentifier::AES_CBC: {
        if (!input.cbc || !input.cbc->iv_present)
            return ExceptionCode::TypeError;
        auto value = makeUnique<CryptoAlgorithmAesCbcCfbParams>(*identifier);
        value->iv = BufferSource(bytesOf(input.cbc->iv));
        params = WTF::move(value);
        break;
    }
    case CryptoAlgorithmIdentifier::AES_CTR: {
        if (!input.ctr || !input.ctr->counter_present || !input.ctr->length_present || input.ctr->length_bits > UINT8_MAX)
            return ExceptionCode::TypeError;
        auto value = makeUnique<CryptoAlgorithmAesCtrParams>(*identifier);
        value->counter = BufferSource(bytesOf(input.ctr->counter));
        value->length = input.ctr->length_bits;
        params = WTF::move(value);
        break;
    }
    case CryptoAlgorithmIdentifier::AES_GCM: {
        if (!input.gcm || !input.gcm->iv_present || (input.gcm->tag_length_present && input.gcm->tag_length_bits > UINT8_MAX))
            return ExceptionCode::TypeError;
        auto value = makeUnique<CryptoAlgorithmAesGcmParams>(*identifier);
        value->iv = BufferSource(bytesOf(input.gcm->iv));
        if (input.gcm->additional_data_present)
            value->additionalData = BufferSource(bytesOf(input.gcm->additional_data));
        if (input.gcm->tag_length_present)
            value->tagLength = static_cast<uint8_t>(input.gcm->tag_length_bits);
        params = WTF::move(value);
        break;
    }
    case CryptoAlgorithmIdentifier::AES_KW:
        params = makeUnique<CryptoAlgorithmParameters>(*identifier);
        break;
    default:
        RELEASE_ASSERT_NOT_REACHED();
    }
    return std::nullopt;
}

bool valid(RanvierCryptoOptionalString value)
{
    return flag(value.present) && (!value.present || valid(value.value));
}

bool valid(const RanvierCryptoOctetJwk* input)
{
    return input && input->size == sizeof(*input) && valid(input->kty) && valid(input->k) && valid(input->alg) && valid(input->use)
        && flag(input->key_ops.present) && (!input->key_ops.present || valid(input->key_ops.value))
        && flag(input->ext_present) && (!input->ext_present || flag(input->ext));
}

String optionalText(RanvierCryptoOptionalString value)
{
    if (!value.present)
        return { };
    return value.value.length ? text(value.value) : emptyString();
}

bool convertJwk(const RanvierCryptoOctetJwk& input, JsonWebKey& jwk)
{
    jwk.kty = optionalText(input.kty);
    jwk.k = optionalText(input.k);
    jwk.alg = optionalText(input.alg);
    jwk.use = optionalText(input.use);
    if (input.ext_present)
        jwk.ext = !!input.ext;
    if (input.key_ops.present) {
        jwk.key_ops = Vector<CryptoKeyUsage>();
        Vector<String> seen;
        bool duplicate = false;
        for (int32_t index = 0; index < input.key_ops.value.count; ++index) {
            auto name = input.key_ops.value.items[index].length ? text(input.key_ops.value.items[index]) : emptyString();
            duplicate |= seen.contains(name);
            seen.append(name);
            if (auto usage = usageOf(name)) {
                jwk.key_ops->append(*usage);
                jwk.usages |= usageBit(*usage);
            }
        }
        return duplicate;
    }
    return false;
}

bool duplicateUsages(const JsonWebKey& jwk)
{
    CryptoKeyUsageBitmap seen = 0;
    if (jwk.key_ops) {
        for (auto usage : *jwk.key_ops) {
            if (seen & usageBit(usage))
                return true;
            seen |= usageBit(usage);
        }
    }
    return false;
}

Vector<uint8_t> utf8Bytes(const String& value)
{
    auto bytes = value.utf8();
    return Vector<uint8_t>(std::span { reinterpret_cast<const uint8_t*>(bytes.data()), bytes.length() });
}

void deliverJwk(uint64_t id, const JsonWebKey& jwk)
{
    auto result = makeUnique<Result>(ResultKind::OctetJwk);
    result->jwk = makeUnique<OwnedOctetJwk>();
    auto& value = *result->jwk;
    value.ktyPresent = !jwk.kty.isNull(); value.kty = utf8Bytes(jwk.kty);
    value.kPresent = !jwk.k.isNull(); value.k = utf8Bytes(jwk.k);
    value.algPresent = !jwk.alg.isNull(); value.alg = utf8Bytes(jwk.alg);
    value.usePresent = !jwk.use.isNull(); value.use = utf8Bytes(jwk.use);
    value.extPresent = jwk.ext.has_value(); value.ext = jwk.ext.value_or(false);
    value.usagesPresent = jwk.key_ops.has_value();
    if (jwk.key_ops) {
        for (auto usage : *jwk.key_ops)
            value.usageStrings.append(utf8Bytes(usageName(usage)));
        for (auto& usage : value.usageStrings)
            value.usageViews.append({ usage.span().data(), static_cast<int32_t>(usage.size()) });
    }
    deliver(id, WTF::move(result));
}

void deliverBytes(uint64_t id, const Vector<uint8_t>& bytes)
{
    auto result = makeUnique<Result>(ResultKind::Bytes);
    result->bytes = bytes;
    deliver(id, WTF::move(result));
}

void importSecret(uint64_t id, CryptoKeyFormat format, KeyData&& data, const CryptoAlgorithmParameters& params, bool extractable, CryptoKeyUsageBitmap usages, bool duplicateJwkUsages = false)
{
    auto wipe = [&] {
        if (auto* bytes = std::get_if<Vector<uint8_t>>(&data))
            secureZeroSpan(bytes->mutableSpan());
    };
    if (params.identifier == CryptoAlgorithmIdentifier::HMAC
        && downcast<CryptoAlgorithmHmacKeyParams>(params).length == 0) {
        wipe();
        deliver(id, errorResult(ExceptionCode::DataError));
        return;
    }
    if (usages & ~allowedUsages(params.identifier)) {
        wipe();
        deliver(id, errorResult(ExceptionCode::SyntaxError));
        return;
    }
    if (auto* jwk = std::get_if<JsonWebKey>(&data); jwk && (duplicateJwkUsages || duplicateUsages(*jwk))) {
        wipe();
        deliver(id, errorResult(ExceptionCode::DataError));
        return;
    }
    auto algorithm = CryptoAlgorithmRegistry::singleton().create(params.identifier);
    if (!algorithm) {
        wipe();
        deliver(id, errorResult(ExceptionCode::NotSupportedError));
        return;
    }
    algorithm->importKey(format, WTF::move(data), params, extractable, usages, [id](CryptoKey& key) { deliverKey(id, key); }, onError(id));
    wipe();
}

void runCipher(uint64_t id, const CryptoAlgorithmParameters& params, Ref<CryptoKey>&& key, Vector<uint8_t>&& bytes, bool decrypting, bool wrapping, CryptoAlgorithm::VectorCallback&& callback)
{
    auto* value = operation(id);
    if (!value || value->result) {
        secureZeroSpan(bytes.mutableSpan());
        return;
    }
    auto algorithm = CryptoAlgorithmRegistry::singleton().create(params.identifier);
    if (!algorithm) {
        secureZeroSpan(bytes.mutableSpan());
        deliver(id, errorResult(ExceptionCode::NotSupportedError));
        return;
    }
    if (wrapping && params.identifier == CryptoAlgorithmIdentifier::AES_KW) {
        if (decrypting)
            algorithm->unwrapKey(WTF::move(key), WTF::move(bytes), WTF::move(callback), onError(id));
        else
            algorithm->wrapKey(WTF::move(key), WTF::move(bytes), WTF::move(callback), onError(id));
    } else if (decrypting)
        algorithm->decrypt(params, WTF::move(key), WTF::move(bytes), WTF::move(callback), onError(id), *value->document, queue());
    else
        algorithm->encrypt(params, WTF::move(key), WTF::move(bytes), WTF::move(callback), onError(id), *value->document, queue());
    secureZeroSpan(bytes.mutableSpan());
}

int32_t startCipher(RvNode* handle, const RanvierCryptoAesCipherParams* input, RanvierCryptoKeyHandle keyHandle, RanvierCryptoBytes data, RanvierCryptoOperationHandle* output, bool decrypting)
{
    Document* document;
    if (auto status = documentOf(handle, document))
        return status;
    if (!output)
        return RV_ERR_NULL_ARGUMENT;
    output->value = 0;
    if (!valid(input) || !valid(data))
        return RV_ERR_NULL_ARGUMENT;
    RefPtr<CryptoKey> key;
    if (auto status = lookupKey(keyHandle, key))
        return status;
    auto id = admit(*document, output);
    std::unique_ptr<CryptoAlgorithmParameters> params;
    if (auto error = cipherParameters(*input, false, params)) {
        deliver(id, errorResult(*error));
        return RV_OK;
    }
    if (key->algorithmIdentifier() != params->identifier || !key->allows(decrypting ? CryptoKeyUsageDecrypt : CryptoKeyUsageEncrypt)) {
        deliver(id, errorResult(ExceptionCode::InvalidAccessError));
        return RV_OK;
    }
    runCipher(id, *params, key.releaseNonNull(), copy(data), decrypting, false,
        [id](const Vector<uint8_t>& bytes) { deliverBytes(id, bytes); });
    return RV_OK;
}

}

int32_t ranvier_crypto_aes_supported(RvNode* handle, RanvierCryptoBytes name, int32_t* supported)
{
    Document* document;
    if (auto status = documentOf(handle, document))
        return status;
    if (!valid(name) || !supported)
        return RV_ERR_NULL_ARGUMENT;
    auto identifier = aesIdentifier(name);
    *supported = identifier && !!CryptoAlgorithmRegistry::singleton().create(*identifier);
    return RV_OK;
}

int32_t ranvier_crypto_aes_generate(RvNode* handle, const RanvierCryptoAesKeyGenParams* input, int32_t extractable, RanvierCryptoStrings requestedUsages, RanvierCryptoOperationHandle* output)
{
    Document* document;
    if (auto status = documentOf(handle, document))
        return status;
    if (!output)
        return RV_ERR_NULL_ARGUMENT;
    output->value = 0;
    if (!input || input->size != sizeof(*input) || !valid(input->name) || !flag(input->length_present) || !flag(extractable) || !valid(requestedUsages))
        return RV_ERR_NULL_ARGUMENT;
    auto id = admit(*document, output);
    CryptoKeyUsageBitmap usages;
    if (auto error = usagesOf(requestedUsages, usages)) {
        deliver(id, errorResult(*error));
        return RV_OK;
    }
    auto identifier = aesIdentifier(input->name);
    if (!identifier) {
        deliver(id, errorResult(ExceptionCode::NotSupportedError));
        return RV_OK;
    }
    if (!input->length_present || input->length_bits > UINT16_MAX) {
        deliver(id, errorResult(ExceptionCode::TypeError));
        return RV_OK;
    }
    CryptoAlgorithmAesKeyParamsInit init;
    init.length = static_cast<uint16_t>(input->length_bits);
    CryptoAlgorithmAesKeyParams params(*identifier, WTF::move(init));
    auto algorithm = CryptoAlgorithmRegistry::singleton().create(*identifier);
    if (!algorithm) {
        deliver(id, errorResult(ExceptionCode::NotSupportedError));
        return RV_OK;
    }
    algorithm->generateKey(params, extractable, usages, [id](KeyOrKeyPair&& result) {
        if (auto* key = std::get_if<Ref<CryptoKey>>(&result))
            deliverKey(id, key->get());
        else
            deliver(id, errorResult(ExceptionCode::OperationError));
    }, onError(id), *document);
    return RV_OK;
}

int32_t ranvier_crypto_secret_import(RvNode* handle, RanvierCryptoBytes formatName, const RanvierCryptoSecretKeyData* input, const RanvierCryptoSecretImportParams* options, int32_t extractable, RanvierCryptoStrings requestedUsages, RanvierCryptoOperationHandle* output)
{
    Document* document;
    if (auto status = documentOf(handle, document))
        return status;
    if (!output)
        return RV_ERR_NULL_ARGUMENT;
    output->value = 0;
    if (!valid(formatName) || !input || input->size != sizeof(*input) || !flag(input->raw_present)
        || (input->raw_present && !valid(input->raw)) || (input->jwk && !valid(input->jwk))
        || !valid(options) || !flag(extractable) || !valid(requestedUsages))
        return RV_ERR_NULL_ARGUMENT;
    auto id = admit(*document, output);
    auto format = formatOf(formatName);
    CryptoKeyUsageBitmap usages;
    JsonWebKey jwk;
    auto usageError = usagesOf(requestedUsages, usages);
    bool duplicateJwkUsages = input->jwk && convertJwk(*input->jwk, jwk);
    if (!format || usageError) {
        deliver(id, errorResult(ExceptionCode::TypeError));
        return RV_OK;
    }
    std::unique_ptr<CryptoAlgorithmParameters> params;
    if (auto error = importParameters(*options, params)) {
        deliver(id, errorResult(*error));
        return RV_OK;
    }
    if ((*format == CryptoKeyFormat::Jwk && (!input->jwk || input->raw_present))
        || (*format != CryptoKeyFormat::Jwk && (!input->raw_present || input->jwk))) {
        deliver(id, errorResult(ExceptionCode::TypeError));
        return RV_OK;
    }
    KeyData data = *format == CryptoKeyFormat::Jwk ? KeyData { WTF::move(jwk) } : KeyData { copy(input->raw) };
    importSecret(id, *format, WTF::move(data), *params, extractable, usages, duplicateJwkUsages);
    return RV_OK;
}

int32_t ranvier_crypto_key_export(RvNode* handle, RanvierCryptoBytes formatName, RanvierCryptoKeyHandle keyHandle, RanvierCryptoOperationHandle* output)
{
    Document* document;
    if (auto status = documentOf(handle, document))
        return status;
    if (!output)
        return RV_ERR_NULL_ARGUMENT;
    output->value = 0;
    if (!valid(formatName))
        return RV_ERR_NULL_ARGUMENT;
    RefPtr<CryptoKey> key;
    if (auto status = lookupKey(keyHandle, key))
        return status;
    auto id = admit(*document, output);
    auto format = formatOf(formatName);
    if (!format) {
        deliver(id, errorResult(ExceptionCode::TypeError));
        return RV_OK;
    }
    if (!key->extractable()) {
        deliver(id, errorResult(ExceptionCode::InvalidAccessError));
        return RV_OK;
    }
    if (!isAes(key->algorithmIdentifier()) && key->algorithmIdentifier() != CryptoAlgorithmIdentifier::HMAC) {
        deliver(id, errorResult(ExceptionCode::NotSupportedError));
        return RV_OK;
    }
    auto algorithm = CryptoAlgorithmRegistry::singleton().create(key->algorithmIdentifier());
    if (!algorithm) {
        deliver(id, errorResult(ExceptionCode::NotSupportedError));
        return RV_OK;
    }
    algorithm->exportKey(*format, key.releaseNonNull(), [id](CryptoKeyFormat, KeyData&& data) {
        if (auto* bytes = std::get_if<Vector<uint8_t>>(&data)) {
            deliverBytes(id, *bytes);
            secureZeroSpan(bytes->mutableSpan());
        } else
            deliverJwk(id, std::get<JsonWebKey>(data));
    }, onError(id));
    return RV_OK;
}

int32_t ranvier_crypto_aes_encrypt(RvNode* handle, const RanvierCryptoAesCipherParams* params, RanvierCryptoKeyHandle key, RanvierCryptoBytes data, RanvierCryptoOperationHandle* output)
{
    return startCipher(handle, params, key, data, output, false);
}

int32_t ranvier_crypto_aes_decrypt(RvNode* handle, const RanvierCryptoAesCipherParams* params, RanvierCryptoKeyHandle key, RanvierCryptoBytes data, RanvierCryptoOperationHandle* output)
{
    return startCipher(handle, params, key, data, output, true);
}

int32_t ranvier_crypto_aes_key_info(RanvierCryptoKeyHandle handle, RanvierCryptoAesKeyInfo* info)
{
    RefPtr<CryptoKey> key;
    if (auto status = lookupKey(handle, key))
        return status;
    if (!info || info->size != sizeof(*info))
        return RV_ERR_NULL_ARGUMENT;
    if (!isAes(key->algorithmIdentifier()))
        return RV_ERR_WRONG_INTERFACE;
    auto metadata = key->algorithm();
    auto* algorithm = std::get_if<CryptoAesKeyAlgorithm>(&metadata);
    if (!algorithm)
        return RV_ERR_WRONG_INTERFACE;
    *info = { sizeof(*info), key->extractable(), algorithm->length,
        key->allows(CryptoKeyUsageEncrypt), key->allows(CryptoKeyUsageDecrypt),
        key->allows(CryptoKeyUsageWrapKey), key->allows(CryptoKeyUsageUnwrapKey) };
    return RV_OK;
}

int32_t ranvier_crypto_key_algorithm_name(RanvierCryptoKeyHandle handle, char* buffer, int32_t capacity, int32_t* length)
{
    RefPtr<CryptoKey> key;
    if (auto status = lookupKey(handle, key))
        return status;
    auto name = utf8Bytes(CryptoAlgorithmRegistry::singleton().name(key->algorithmIdentifier()));
    return copyBytes(name.span(), reinterpret_cast<uint8_t*>(buffer), capacity, length);
}

int32_t ranvier_crypto_key_type(RanvierCryptoKeyHandle handle, char* buffer, int32_t capacity, int32_t* length)
{
    RefPtr<CryptoKey> key;
    if (auto status = lookupKey(handle, key))
        return status;
    String type;
    switch (key->type()) {
    case CryptoKeyType::Secret: type = "secret"_s; break;
    case CryptoKeyType::Public: type = "public"_s; break;
    case CryptoKeyType::Private: type = "private"_s; break;
    }
    auto bytes = utf8Bytes(type);
    return copyBytes(bytes.span(), reinterpret_cast<uint8_t*>(buffer), capacity, length);
}

int32_t ranvier_crypto_operation_octet_jwk(RanvierCryptoOperationHandle handle, RanvierCryptoOctetJwk* output)
{
    Result* result;
    if (auto status = resultOf(handle, ResultKind::OctetJwk, result))
        return status;
    if (!output || output->size != sizeof(*output))
        return RV_ERR_NULL_ARGUMENT;
    auto& value = *result->jwk;
    auto field = [](bool present, const Vector<uint8_t>& bytes) -> RanvierCryptoOptionalString {
        return { present, { bytes.span().data(), static_cast<int32_t>(bytes.size()) } };
    };
    *output = { sizeof(*output), field(value.ktyPresent, value.kty), field(value.kPresent, value.k),
        field(value.algPresent, value.alg), field(value.usePresent, value.use),
        { value.usagesPresent, { value.usageViews.span().data(), static_cast<int32_t>(value.usageViews.size()) } }, value.extPresent, value.ext };
    return RV_OK;
}

namespace {

Vector<uint8_t> encodeJwk(const JsonWebKey& jwk)
{
    auto object = JSON::Object::create();
    if (!jwk.kty.isNull()) object->setString("kty"_s, jwk.kty);
    if (!jwk.k.isNull()) object->setString("k"_s, jwk.k);
    if (!jwk.alg.isNull()) object->setString("alg"_s, jwk.alg);
    if (!jwk.use.isNull()) object->setString("use"_s, jwk.use);
    if (jwk.ext) object->setBoolean("ext"_s, *jwk.ext);
    if (jwk.key_ops) {
        auto usages = JSON::Array::create();
        for (auto usage : *jwk.key_ops)
            usages->pushString(usageName(usage));
        object->setArray("key_ops"_s, WTF::move(usages));
    }
    return utf8Bytes(object->toJSONString());
}

String jsonString(JSON::Value& value)
{
    switch (value.type()) {
    case JSON::Value::Type::String:
        return value.asString();
    case JSON::Value::Type::Null:
        return "null"_s;
    case JSON::Value::Type::Object:
        return "[object Object]"_s;
    case JSON::Value::Type::Array: {
        auto array = value.asArray();
        StringBuilder builder;
        for (size_t index = 0; index < array->length(); ++index) {
            if (index)
                builder.append(',');
            auto item = array->get(index);
            if (!item->isNull())
                builder.append(jsonString(item));
        }
        return builder.toString();
    }
    case JSON::Value::Type::Boolean:
    case JSON::Value::Type::Integer:
    case JSON::Value::Type::Double:
        return value.toJSONString();
    }
    RELEASE_ASSERT_NOT_REACHED();
}

bool jsonBoolean(JSON::Value& value)
{
    switch (value.type()) {
    case JSON::Value::Type::Null: return false;
    case JSON::Value::Type::Boolean: return *value.asBoolean();
    case JSON::Value::Type::String: return !value.asString().isEmpty();
    case JSON::Value::Type::Integer:
    case JSON::Value::Type::Double: return value.asDouble().value_or(0) != 0;
    case JSON::Value::Type::Object:
    case JSON::Value::Type::Array: return true;
    }
    RELEASE_ASSERT_NOT_REACHED();
}

std::optional<ExceptionCode> decodeJwk(const Vector<uint8_t>& bytes, JsonWebKey& jwk, bool& duplicateJwkUsages)
{
    auto string = String::fromUTF8(bytes.span());
    auto value = JSON::Value::parseJSON(string);
    if (!value)
        return ExceptionCode::DataError;
    auto object = value->asObject();
    if (!object) {
        if (value->isNull() || value->type() == JSON::Value::Type::Array)
            return std::nullopt;
        return ExceptionCode::DataError;
    }
    auto field = [&](ASCIILiteral name) -> String {
        auto value = object->getValue(name);
        return value ? jsonString(*value) : String { };
    };
    jwk.kty = field("kty"_s);
    jwk.k = field("k"_s);
    jwk.alg = field("alg"_s);
    jwk.use = field("use"_s);
    if (auto ext = object->getValue("ext"_s))
        jwk.ext = jsonBoolean(*ext);
    if (auto value = object->getValue("key_ops"_s)) {
        auto array = value->asArray();
        if (!array)
            return ExceptionCode::DataError;
        jwk.key_ops = Vector<CryptoKeyUsage>();
        Vector<String> seen;
        for (auto& item : *array) {
            auto name = jsonString(item);
            duplicateJwkUsages |= seen.contains(name);
            seen.append(name);
            if (auto usage = usageOf(name)) {
                jwk.key_ops->append(*usage);
                jwk.usages |= usageBit(*usage);
            }
        }
    }
    return std::nullopt;
}

}

int32_t ranvier_crypto_aes_wrap(RvNode* handle, RanvierCryptoBytes formatName, RanvierCryptoKeyHandle keyHandle, RanvierCryptoKeyHandle wrappingHandle, const RanvierCryptoAesCipherParams* input, RanvierCryptoOperationHandle* output)
{
    Document* document;
    if (auto status = documentOf(handle, document))
        return status;
    if (!output)
        return RV_ERR_NULL_ARGUMENT;
    output->value = 0;
    if (!valid(formatName) || !valid(input))
        return RV_ERR_NULL_ARGUMENT;
    RefPtr<CryptoKey> key, wrapping;
    if (auto status = lookupKey(keyHandle, key))
        return status;
    if (auto status = lookupKey(wrappingHandle, wrapping))
        return status;
    auto id = admit(*document, output);
    auto format = formatOf(formatName);
    if (!format) {
        deliver(id, errorResult(ExceptionCode::TypeError));
        return RV_OK;
    }
    std::unique_ptr<CryptoAlgorithmParameters> params;
    if (auto error = cipherParameters(*input, true, params)) {
        deliver(id, errorResult(*error));
        return RV_OK;
    }
    if (wrapping->algorithmIdentifier() != params->identifier || !wrapping->allows(CryptoKeyUsageWrapKey)) {
        deliver(id, errorResult(ExceptionCode::InvalidAccessError));
        return RV_OK;
    }
    if (!isAes(key->algorithmIdentifier()) && key->algorithmIdentifier() != CryptoAlgorithmIdentifier::HMAC) {
        deliver(id, errorResult(ExceptionCode::NotSupportedError));
        return RV_OK;
    }
    if (!key->extractable()) {
        deliver(id, errorResult(ExceptionCode::InvalidAccessError));
        return RV_OK;
    }
    auto algorithm = CryptoAlgorithmRegistry::singleton().create(key->algorithmIdentifier());
    if (!algorithm) {
        deliver(id, errorResult(ExceptionCode::NotSupportedError));
        return RV_OK;
    }
    algorithm->exportKey(*format, key.releaseNonNull(), [id, wrapping = wrapping.releaseNonNull(), params = WTF::move(params)](CryptoKeyFormat, KeyData&& data) mutable {
        auto* value = operation(id);
        if (!value || value->result) {
            if (auto* raw = std::get_if<Vector<uint8_t>>(&data))
                secureZeroSpan(raw->mutableSpan());
            return;
        }
        Vector<uint8_t> bytes;
        if (auto* raw = std::get_if<Vector<uint8_t>>(&data))
            bytes = WTF::move(*raw);
        else
            bytes = encodeJwk(std::get<JsonWebKey>(data));
        runCipher(id, *params, WTF::move(wrapping), WTF::move(bytes), false, true,
            [id](const Vector<uint8_t>& result) { deliverBytes(id, result); });
    }, onError(id));
    return RV_OK;
}

int32_t ranvier_crypto_aes_unwrap(RvNode* handle, RanvierCryptoBytes formatName, RanvierCryptoBytes wrapped, RanvierCryptoKeyHandle unwrappingHandle, const RanvierCryptoAesCipherParams* input, const RanvierCryptoSecretImportParams* options, int32_t extractable, RanvierCryptoStrings requestedUsages, RanvierCryptoOperationHandle* output)
{
    Document* document;
    if (auto status = documentOf(handle, document))
        return status;
    if (!output)
        return RV_ERR_NULL_ARGUMENT;
    output->value = 0;
    if (!valid(formatName) || !valid(wrapped) || !valid(input) || !valid(options) || !flag(extractable) || !valid(requestedUsages))
        return RV_ERR_NULL_ARGUMENT;
    RefPtr<CryptoKey> key;
    if (auto status = lookupKey(unwrappingHandle, key))
        return status;
    auto id = admit(*document, output);
    auto format = formatOf(formatName);
    CryptoKeyUsageBitmap usages;
    if (!format || usagesOf(requestedUsages, usages)) {
        deliver(id, errorResult(ExceptionCode::TypeError));
        return RV_OK;
    }
    std::unique_ptr<CryptoAlgorithmParameters> params, importParams;
    if (auto error = cipherParameters(*input, true, params)) {
        deliver(id, errorResult(*error));
        return RV_OK;
    }
    if (auto error = importParameters(*options, importParams)) {
        deliver(id, errorResult(*error));
        return RV_OK;
    }
    if (key->algorithmIdentifier() != params->identifier || !key->allows(CryptoKeyUsageUnwrapKey)) {
        deliver(id, errorResult(ExceptionCode::InvalidAccessError));
        return RV_OK;
    }
    runCipher(id, *params, key.releaseNonNull(), copy(wrapped), true, true,
        [id, format = *format, params = WTF::move(importParams), extractable, usages](const Vector<uint8_t>& bytes) {
            auto* value = operation(id);
            if (!value || value->result)
                return;
            KeyData data;
            bool duplicateJwkUsages = false;
            if (format == CryptoKeyFormat::Jwk) {
                JsonWebKey jwk;
                if (auto error = decodeJwk(bytes, jwk, duplicateJwkUsages)) {
                    deliver(id, errorResult(*error));
                    return;
                }
                data = WTF::move(jwk);
            } else
                data = bytes;
            importSecret(id, format, WTF::move(data), *params, extractable, usages, duplicateJwkUsages);
        });
    return RV_OK;
}
