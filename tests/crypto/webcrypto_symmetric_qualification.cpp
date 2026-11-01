#include "config.h"
#include "webcrypto_symmetric_qualification_contract.h"

#include "BufferSource.h"
#include "CryptoAlgorithmAESCBC.h"
#include "CryptoAlgorithmAESCTR.h"
#include "CryptoAlgorithmAESGCM.h"
#include "CryptoAlgorithmAESKW.h"
#include "CryptoAlgorithmHKDF.h"
#include "CryptoAlgorithmPBKDF2.h"
#include "CryptoAlgorithmAesCbcCfbParams.h"
#include "CryptoAlgorithmAesCtrParams.h"
#include "CryptoAlgorithmAesGcmParams.h"
#include "CryptoAlgorithmAesKeyParams.h"
#include "CryptoAlgorithmAesKeyParamsInit.h"
#include "CryptoAlgorithmHkdfParams.h"
#include "CryptoAlgorithmPbkdf2Params.h"
#include "CryptoKeyAES.h"
#include "CryptoAesKeyAlgorithm.h"
#include "Document.h"
#include "ExceptionCode.h"
#include "ExceptionOr.h"
#include "Node.h"
#include "RanvierWebCoreAbi.h"
#include <array>
#include <thread>
#include <wtf/RefPtr.h>
#include <wtf/StdLibExtras.h>
#include <wtf/ThreadSafeRefCounted.h>
#include <wtf/WorkQueue.h>

using namespace WebCore;

namespace {

RefPtr<CryptoAlgorithm> algorithm(SymmetricAlgorithm value)
{
    switch (value) {
    case SymmetricAlgorithm::CBC: return CryptoAlgorithmAESCBC::create();
    case SymmetricAlgorithm::CTR: return CryptoAlgorithmAESCTR::create();
    case SymmetricAlgorithm::GCM: return CryptoAlgorithmAESGCM::create();
    case SymmetricAlgorithm::KW: return CryptoAlgorithmAESKW::create();
    case SymmetricAlgorithm::HKDF: return CryptoAlgorithmHKDF::create();
    case SymmetricAlgorithm::PBKDF2: return CryptoAlgorithmPBKDF2::create();
    }
    return nullptr;
}

CryptoAlgorithmIdentifier hashAlgorithm(int32_t value)
{
    switch (value) {
    case 1: return CryptoAlgorithmIdentifier::SHA_1;
    case 256: return CryptoAlgorithmIdentifier::SHA_256;
    case 384: return CryptoAlgorithmIdentifier::SHA_384;
    case 512: return CryptoAlgorithmIdentifier::SHA_512;
    }
    return CryptoAlgorithmIdentifier::SHA_256;
}

const char* exceptionName(ExceptionCode code)
{
    switch (code) {
    case ExceptionCode::OperationError: return "OperationError";
    case ExceptionCode::SyntaxError: return "SyntaxError";
    case ExceptionCode::DataError: return "DataError";
    case ExceptionCode::NotSupportedError: return "NotSupportedError";
    case ExceptionCode::InvalidAccessError: return "InvalidAccessError";
    default: return "OtherBackendException";
    }
}

bool valid(RanvierCryptoBytes bytes)
{
    return bytes.length >= 0 && (!bytes.length || bytes.data);
}

Vector<uint8_t> copy(RanvierCryptoBytes bytes)
{
    return Vector<uint8_t> { std::span(bytes.data, static_cast<size_t>(bytes.length)) };
}

class Operation final : public ThreadSafeRefCounted<Operation> {
public:
    Operation(Document& document, const SymmetricQualificationRequest& request,
        Ref<CryptoAlgorithm>&& implementation, SymmetricQualificationCallback callback, void* context)
        : m_document(document)
        , m_request(request)
        , m_algorithm(WTF::move(implementation))
        , m_callback(callback)
        , m_context(context)
        , m_owner(std::this_thread::get_id())
        , m_queue(WorkQueue::create("RanvierSymmetricQualification"_s))
        , m_material(copy(request.key))
        , m_iv(copy(request.iv))
        , m_aad(copy(request.additionalData))
        , m_input(copy(request.input))
        , m_salt(copy(request.salt))
        , m_info(copy(request.info))
    {
    }

    bool owner() const { return m_owner == std::this_thread::get_id(); }
    bool finished() const { return m_terminalCount; }
    void barrier() { m_queue->dispatchSync([] { }); }
    std::optional<RanvierCryptoBytes> input(int32_t field) const
    {
        std::array<const Vector<uint8_t>*, 6> values { &m_material, &m_iv, &m_aad, &m_input, &m_salt, &m_info };
        if (field < 0 || static_cast<size_t>(field) >= values.size())
            return std::nullopt;
        auto& bytes = *values[field];
        return RanvierCryptoBytes { bytes.span().data(), static_cast<int32_t>(bytes.size()) };
    }

    void begin()
    {
        m_duringStart = true;
        auto fail = [self = Ref { *this }](ExceptionCode code) { self->fail(code); };
        if (operation() == SymmetricOperation::GenerateExport) {
            CryptoAlgorithmAesKeyParamsInit init { };
            init.length = m_request.lengthBits;
            CryptoAlgorithmAesKeyParams params { m_algorithm->identifier(), WTF::move(init) };
            m_algorithm->generateKey(params, m_request.extractable, usages(),
                [self = Ref { *this }](KeyOrKeyPair&& value) {
                    auto* key = std::get_if<Ref<CryptoKey>>(&value);
                    if (!key) {
                        self->fail(ExceptionCode::OperationError);
                        return;
                    }
                    self->m_key = key->ptr();
                    self->continueAfterKey();
                }, WTF::move(fail), m_document);
        } else {
            CryptoAlgorithmParameters params { m_algorithm->identifier() };
            m_algorithm->importKey(CryptoKeyFormat::Raw, KeyData { Vector<uint8_t> { m_material } }, params,
                m_request.extractable, usages(),
                [self = Ref { *this }](CryptoKey& key) {
                    self->m_key = &key;
                    ++self->m_borrowedRetains;
                    self->continueAfterKey();
                }, WTF::move(fail));
        }
        m_duringStart = false;
    }

private:
    SymmetricOperation operation() const { return static_cast<SymmetricOperation>(m_request.operation); }
    SymmetricAlgorithm family() const { return static_cast<SymmetricAlgorithm>(m_request.algorithm); }
    CryptoKeyUsageBitmap usages() const
    {
        if (family() == SymmetricAlgorithm::HKDF || family() == SymmetricAlgorithm::PBKDF2)
            return CryptoKeyUsageDeriveBits | CryptoKeyUsageDeriveKey;
        if (family() == SymmetricAlgorithm::KW)
            return CryptoKeyUsageWrapKey | CryptoKeyUsageUnwrapKey;
        return CryptoKeyUsageEncrypt | CryptoKeyUsageDecrypt | CryptoKeyUsageWrapKey | CryptoKeyUsageUnwrapKey;
    }

    void continueAfterKey()
    {
        // Run after the borrowed import callback returns, while the fixture owns the retained key.
        m_document->postTask([self = Ref { *this }](auto&) { self->perform(); });
    }

    void finish(const Vector<uint8_t>& output, std::optional<ExceptionCode> exception = std::nullopt)
    {
        ++m_terminalCount;
        SymmetricQualificationResult result { };
        result.size = sizeof(result);
        result.exceptionCode = exception ? static_cast<int32_t>(*exception) : 0;
        result.exceptionName = exception ? exceptionName(*exception) : nullptr;
        result.ownerThread = owner();
        result.callbackDuringStart = m_duringStart;
        result.backendCallbackInline = m_inBackendCall;
        result.borrowedKeyRetains = m_borrowedRetains;
        result.terminalCount = m_terminalCount;
        if (m_key) {
            auto algorithm = m_key->algorithm();
            if (auto* aes = std::get_if<CryptoAesKeyAlgorithm>(&algorithm))
                result.keyBits = aes->length;
            else {
                auto data = m_key->data();
                result.keyBits = data.key ? data.key->size() * 8 : 0;
            }
            result.extractable = m_key->extractable();
            result.usages = m_key->usagesBitmap();
        }
        result.output = { output.span().data(), static_cast<int32_t>(output.size()) };
        m_callback(m_context, &result);
    }

    void fail(ExceptionCode code) { finish({ }, code); }

    void exportKey()
    {
        m_inBackendCall = true;
        m_algorithm->exportKey(CryptoKeyFormat::Raw, Ref<CryptoKey> { *m_key },
            [self = Ref { *this }](CryptoKeyFormat format, KeyData&& data) {
                auto* bytes = std::get_if<Vector<uint8_t>>(&data);
                if (format != CryptoKeyFormat::Raw || !bytes) {
                    self->fail(ExceptionCode::OperationError);
                    return;
                }
                self->finish(*bytes);
            }, [self = Ref { *this }](ExceptionCode code) { self->fail(code); });
        m_inBackendCall = false;
    }

    void derived(const Vector<uint8_t>& bytes)
    {
        if (operation() != SymmetricOperation::DeriveImportExport) {
            finish(bytes);
            return;
        }
        m_algorithm = CryptoAlgorithmAESGCM::create();
        CryptoAlgorithmParameters params { m_algorithm->identifier() };
        m_algorithm->importKey(CryptoKeyFormat::Raw, KeyData { Vector<uint8_t> { bytes } }, params, true,
            CryptoKeyUsageEncrypt | CryptoKeyUsageDecrypt,
            [self = Ref { *this }](CryptoKey& key) {
                self->m_key = &key;
                ++self->m_borrowedRetains;
                self->m_document->postTask([self = Ref { self.get() }](auto&) { self->exportKey(); });
            }, [self = Ref { *this }](ExceptionCode code) { self->fail(code); });
    }

    void perform()
    {
        if (!owner()) {
            fail(ExceptionCode::OperationError);
            return;
        }
        if (operation() == SymmetricOperation::Export || operation() == SymmetricOperation::GenerateExport) {
            exportKey();
            return;
        }
        if (operation() == SymmetricOperation::ImportInfo) {
            finish({ });
            return;
        }
        std::unique_ptr<CryptoAlgorithmParameters> params;
        switch (family()) {
        case SymmetricAlgorithm::CBC: {
            auto value = makeUnique<CryptoAlgorithmAesCbcCfbParams>(m_algorithm->identifier());
            value->iv = BufferSource { m_iv.span() };
            params = WTF::move(value);
            break;
        }
        case SymmetricAlgorithm::CTR: {
            auto value = makeUnique<CryptoAlgorithmAesCtrParams>(m_algorithm->identifier());
            value->counter = BufferSource { m_iv.span() };
            value->length = m_request.parameter;
            params = WTF::move(value);
            break;
        }
        case SymmetricAlgorithm::GCM: {
            auto value = makeUnique<CryptoAlgorithmAesGcmParams>(m_algorithm->identifier());
            value->iv = BufferSource { m_iv.span() };
            value->additionalData = BufferSource { m_aad.span() };
            if (m_request.parameter >= 0)
                value->tagLength = m_request.parameter;
            params = WTF::move(value);
            break;
        }
        case SymmetricAlgorithm::HKDF: {
            auto value = makeUnique<CryptoAlgorithmHkdfParams>(m_algorithm->identifier());
            value->hashIdentifier = hashAlgorithm(m_request.hash);
            if (m_request.saltPresent)
                value->salt = BufferSource { m_salt.span() };
            value->info = BufferSource { m_info.span() };
            params = WTF::move(value);
            break;
        }
        case SymmetricAlgorithm::PBKDF2: {
            auto value = makeUnique<CryptoAlgorithmPbkdf2Params>(m_algorithm->identifier());
            value->hashIdentifier = hashAlgorithm(m_request.hash);
            value->iterations = m_request.iterations;
            value->salt = BufferSource { m_salt.span() };
            params = WTF::move(value);
            break;
        }
        case SymmetricAlgorithm::KW:
            params = makeUnique<CryptoAlgorithmParameters>(m_algorithm->identifier());
            break;
        }
        auto callback = [self = Ref { *this }](const Vector<uint8_t>& bytes) { self->finish(bytes); };
        auto fail = [self = Ref { *this }](ExceptionCode code) { self->fail(code); };
        m_inBackendCall = true;
        switch (operation()) {
        case SymmetricOperation::Encrypt:
            m_algorithm->encrypt(*params, Ref<CryptoKey> { *m_key }, WTF::move(m_input), WTF::move(callback), WTF::move(fail), m_document, m_queue);
            break;
        case SymmetricOperation::Decrypt:
            m_algorithm->decrypt(*params, Ref<CryptoKey> { *m_key }, WTF::move(m_input), WTF::move(callback), WTF::move(fail), m_document, m_queue);
            break;
        case SymmetricOperation::Wrap:
            m_algorithm->wrapKey(Ref<CryptoKey> { *m_key }, WTF::move(m_input), WTF::move(callback), WTF::move(fail));
            break;
        case SymmetricOperation::Unwrap:
            m_algorithm->unwrapKey(Ref<CryptoKey> { *m_key }, WTF::move(m_input), WTF::move(callback), WTF::move(fail));
            break;
        case SymmetricOperation::DeriveBits:
        case SymmetricOperation::DeriveImportExport: {
            std::optional<size_t> length;
            if (m_request.lengthBits >= 0)
                length = m_request.lengthBits;
            if (operation() == SymmetricOperation::DeriveImportExport) {
                CryptoAlgorithmAesKeyParamsInit init { };
                init.length = m_request.lengthBits;
                CryptoAlgorithmAesKeyParams target { CryptoAlgorithmIdentifier::AES_GCM, WTF::move(init) };
                auto targetAlgorithm = CryptoAlgorithmAESGCM::create();
                auto result = targetAlgorithm->getKeyLength(target);
                if (result.hasException()) {
                    fail(result.releaseException().code());
                    break;
                }
                length = result.releaseReturnValue();
            }
            m_algorithm->deriveBits(*params, Ref<CryptoKey> { *m_key }, length,
                [self = Ref { *this }](const Vector<uint8_t>& bytes) { self->derived(bytes); },
                WTF::move(fail), m_document, m_queue);
            break;
        }
        case SymmetricOperation::CbcRawEncrypt:
        case SymmetricOperation::CbcRawDecrypt: {
            auto& cbc = downcast<CryptoAlgorithmAesCbcCfbParams>(*params);
            auto& key = downcast<CryptoKeyAES>(*m_key);
            auto result = operation() == SymmetricOperation::CbcRawEncrypt
                ? CryptoAlgorithmAESCBC::platformEncrypt(cbc, key, m_input, CryptoAlgorithmAESCBC::Padding::No)
                : CryptoAlgorithmAESCBC::platformDecrypt(cbc, key, m_input, CryptoAlgorithmAESCBC::Padding::No);
            if (result.hasException())
                fail(result.releaseException().code());
            else
                callback(result.releaseReturnValue());
            break;
        }
        default:
            fail(ExceptionCode::NotSupportedError);
            break;
        }
        m_inBackendCall = false;
    }

    Ref<Document> m_document;
    SymmetricQualificationRequest m_request;
    Ref<CryptoAlgorithm> m_algorithm;
    SymmetricQualificationCallback m_callback;
    void* m_context;
    std::thread::id m_owner;
    Ref<WorkQueue> m_queue;
    RefPtr<CryptoKey> m_key;
    Vector<uint8_t> m_material, m_iv, m_aad, m_input, m_salt, m_info;
    bool m_duringStart { false };
    bool m_inBackendCall { false };
    int32_t m_borrowedRetains { 0 };
    int32_t m_terminalCount { 0 };
};

}

extern "C" WEBCORE_EXPORT int32_t ranvier_test_symmetric_request_size() { return sizeof(SymmetricQualificationRequest); }
extern "C" WEBCORE_EXPORT int32_t ranvier_test_symmetric_result_size() { return sizeof(SymmetricQualificationResult); }

extern "C" WEBCORE_EXPORT void* ranvier_test_symmetric_start(RvNode* node,
    const SymmetricQualificationRequest* request, SymmetricQualificationCallback callback, void* context)
{
    if (!node || !request || !callback || request->size != sizeof(*request))
        return nullptr;
    for (auto bytes : { request->key, request->iv, request->additionalData, request->input, request->salt, request->info }) {
        if (!valid(bytes))
            return nullptr;
    }
    auto* document = dynamicDowncast<Document>(reinterpret_cast<Node*>(node));
    auto implementation = algorithm(static_cast<SymmetricAlgorithm>(request->algorithm));
    if (!document || !implementation)
        return nullptr;
    auto operation = adoptRef(*new Operation(*document, *request, implementation.releaseNonNull(), callback, context));
    operation->begin();
    return &operation.leakRef();
}

extern "C" WEBCORE_EXPORT int32_t ranvier_test_symmetric_barrier(void* token)
{
    if (!token)
        return -1;
    auto& operation = *static_cast<Operation*>(token);
    if (!operation.owner())
        return -2;
    operation.barrier();
    return 0;
}

extern "C" WEBCORE_EXPORT int32_t ranvier_test_symmetric_input(void* token, int32_t field, RanvierCryptoBytes* output)
{
    if (!token || !output)
        return -1;
    auto& operation = *static_cast<Operation*>(token);
    if (!operation.owner())
        return -2;
    auto bytes = operation.input(field);
    if (!bytes)
        return -1;
    *output = *bytes;
    return 0;
}

extern "C" WEBCORE_EXPORT int32_t ranvier_test_symmetric_release(void* token)
{
    if (!token)
        return -1;
    auto& operation = *static_cast<Operation*>(token);
    if (!operation.owner())
        return -2;
    operation.barrier();
    if (!operation.finished())
        return -3;
    operation.deref();
    return 0;
}
