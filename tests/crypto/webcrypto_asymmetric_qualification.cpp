#include "config.h"
#include "webcrypto_asymmetric_qualification_contract.h"

#include "BufferSource.h"
#include "CryptoAlgorithmECDH.h"
#include "CryptoAlgorithmECDSA.h"
#include "CryptoAlgorithmRSA_OAEP.h"
#include "CryptoAlgorithmRSA_PSS.h"
#include "CryptoAlgorithmRSASSA_PKCS1_v1_5.h"
#include "CryptoAlgorithmX25519.h"
#include "CryptoAlgorithmAESGCM.h"
#include "CryptoAlgorithmEcKeyParams.h"
#include "CryptoAlgorithmEcdhKeyDeriveParams.h"
#include "CryptoAlgorithmEcdsaParams.h"
#include "CryptoAlgorithmRsaHashedImportParams.h"
#include "CryptoAlgorithmRsaHashedKeyGenParams.h"
#include "CryptoAlgorithmRsaOaepParams.h"
#include "CryptoAlgorithmRsaPssParams.h"
#include "CryptoEcKeyAlgorithm.h"
#include "CryptoRsaHashedKeyAlgorithm.h"
#include "Document.h"
#include "ExceptionCode.h"
#include "Node.h"
#include "RanvierWebCoreAbi.h"
#include <array>
#include <thread>
#include <wtf/ThreadSafeRefCounted.h>
#include <wtf/WorkQueue.h>
#include <wtf/text/CString.h>
#include <wtf/text/Base64.h>
#if USE(GCRYPT)
#include <gcrypt.h>
#endif

using namespace WebCore;

namespace {
RefPtr<CryptoAlgorithm> implementation(int value)
{
    switch (value) {
    case 1: return CryptoAlgorithmRSASSA_PKCS1_v1_5::create();
    case 2: return CryptoAlgorithmRSA_PSS::create();
    case 3: return CryptoAlgorithmRSA_OAEP::create();
    case 4: return CryptoAlgorithmECDSA::create();
    case 5: return CryptoAlgorithmECDH::create();
    }
    return nullptr;
}
CryptoAlgorithmIdentifier hash(int value)
{
    switch (value) {
    case 1: return CryptoAlgorithmIdentifier::SHA_1;
    case 384: return CryptoAlgorithmIdentifier::SHA_384;
    case 512: return CryptoAlgorithmIdentifier::SHA_512;
    default: return CryptoAlgorithmIdentifier::SHA_256;
    }
}
String curve(int value)
{
    switch (value) {
    case 256: return "P-256"_s;
    case 384: return "P-384"_s;
    case 521: return "P-521"_s;
    default: return "invalid-curve"_s;
    }
}
CryptoKeyFormat format(int value)
{
    switch (value) {
    case 1: return CryptoKeyFormat::Raw;
    case 2: return CryptoKeyFormat::Jwk;
    case 3: return CryptoKeyFormat::Spki;
    default: return CryptoKeyFormat::Pkcs8;
    }
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
Vector<uint8_t> copy(AsymmetricBytes value) { return Vector<uint8_t> { std::span(value.data, static_cast<size_t>(value.length)) }; }
AsymmetricBytes bytes(const Vector<uint8_t>& value) { return { value.span().data(), static_cast<int32_t>(value.size()) }; }
AsymmetricBytes bytes(const CString& value) { return { reinterpret_cast<const uint8_t*>(value.data()), static_cast<int32_t>(value.length()) }; }
std::array<String JsonWebKey::*, 14> fields { &JsonWebKey::kty, &JsonWebKey::crv, &JsonWebKey::x, &JsonWebKey::y,
    &JsonWebKey::d, &JsonWebKey::n, &JsonWebKey::e, &JsonWebKey::p, &JsonWebKey::q, &JsonWebKey::dp,
    &JsonWebKey::dq, &JsonWebKey::qi, &JsonWebKey::alg, &JsonWebKey::use };

struct KeyHandle {
    Ref<Document> document;
    Ref<CryptoKey> key;
    std::thread::id owner;
};

class Operation final : public ThreadSafeRefCounted<Operation> {
public:
    Operation(Document& document, const AsymmetricRequest& request, Ref<CryptoAlgorithm>&& algorithm,
        AsymmetricCallback callback, void* context)
        : m_document(document), m_request(request), m_algorithm(WTF::move(algorithm)), m_callback(callback), m_context(context)
        , m_owner(std::this_thread::get_id()), m_queue(WorkQueue::create("RanvierAsymmetricQualification"_s))
        , m_input(copy(request.input)), m_signature(copy(request.signature)), m_label(copy(request.label)), m_exponent(copy(request.exponent))
    {
        if (request.key)
            m_key = static_cast<KeyHandle*>(request.key)->key.ptr();
        if (request.peer)
            m_peer = static_cast<KeyHandle*>(request.peer)->key.ptr();
        for (size_t i = 0; i < fields.size(); ++i) {
            if (request.jwk[i].data)
                m_jwk.*fields[i] = String::fromUTF8(std::span(request.jwk[i].data, static_cast<size_t>(request.jwk[i].length)));
        }
        if (request.jwkExt >= 0)
            m_jwk.ext = !!request.jwkExt;
    }
    bool owner() const { return m_owner == std::this_thread::get_id(); }
    bool finished() const { return m_terminalCount; }
    void barrier() { m_queue->dispatchSync([] { }); }
    std::optional<AsymmetricBytes> input(int field) const
    {
        std::array<const Vector<uint8_t>*, 4> values { &m_input, &m_signature, &m_label, &m_exponent };
        if (field < 0 || static_cast<size_t>(field) >= values.size())
            return std::nullopt;
        return bytes(*values[field]);
    }
    void begin()
    {
        m_duringStart = true;
        if (m_request.operation == 1) {
            std::unique_ptr<CryptoAlgorithmParameters> parameters;
            if (m_request.algorithm <= 3) {
                CryptoAlgorithmRsaHashedKeyGenParamsInit init { { { }, static_cast<size_t>(m_request.parameter), Uint8Array::create(ArrayBuffer::create(m_exponent.span())) }, { } };
                parameters = makeUnique<CryptoAlgorithmRsaHashedKeyGenParams>(m_algorithm->identifier(), WTF::move(init), hash(m_request.hash));
            } else {
                auto ec = makeUnique<CryptoAlgorithmEcKeyParams>(m_algorithm->identifier());
                ec->namedCurve = curve(m_request.curve);
                parameters = WTF::move(ec);
            }
            m_algorithm->generateKey(*parameters, m_request.extractable, m_request.usages,
                [self = Ref { *this }](KeyOrKeyPair&& result) {
                    auto* pair = std::get_if<CryptoKeyPair>(&result);
                    if (!pair || !pair->publicKey || !pair->privateKey) {
                        self->fail(ExceptionCode::OperationError);
                        return;
                    }
                    self->m_key = pair->publicKey;
                    self->m_second = pair->privateKey;
                    self->later();
                }, [self = Ref { *this }](ExceptionCode code) { self->fail(code); }, m_document);
        } else if (m_request.operation == 2) {
            std::unique_ptr<CryptoAlgorithmParameters> parameters;
            if (m_request.algorithm <= 3) {
                auto rsa = makeUnique<CryptoAlgorithmRsaHashedImportParams>(m_algorithm->identifier());
                rsa->hashIdentifier = hash(m_request.hash);
                parameters = WTF::move(rsa);
            } else {
                auto ec = makeUnique<CryptoAlgorithmEcKeyParams>(m_algorithm->identifier());
                ec->namedCurve = curve(m_request.curve);
                parameters = WTF::move(ec);
            }
            KeyData data = m_request.format == 2 ? KeyData { WTF::move(m_jwk) } : KeyData { Vector<uint8_t> { m_input } };
            m_algorithm->importKey(format(m_request.format), WTF::move(data), *parameters, m_request.extractable, m_request.usages,
                [self = Ref { *this }](CryptoKey& key) {
                    self->m_key = &key;
                    ++self->m_borrowedRetains;
                    self->later();
                }, [self = Ref { *this }](ExceptionCode code) { self->fail(code); });
        } else
            later();
        m_duringStart = false;
    }
private:
    void later() { m_document->postTask([self = Ref { *this }](auto&) { self->perform(); }); }
    void fail(ExceptionCode code) { finish({ }, code); }
    void finish(const Vector<uint8_t>& output, std::optional<ExceptionCode> exception = std::nullopt, const JsonWebKey* jwk = nullptr, int verified = -1)
    {
        AsymmetricResult result { };
        result.size = sizeof(result);
        result.exceptionCode = exception ? static_cast<int>( *exception) : 0;
        result.exceptionName = exception ? exceptionName(*exception) : nullptr;
        result.ownerThread = owner();
        result.terminalCount = ++m_terminalCount;
        result.callbackDuringStart = m_duringStart;
        result.borrowedRetains = m_borrowedRetains;
        result.verified = verified;
        result.algorithm = m_request.algorithm;
        result.output = bytes(output);
        Vector<uint8_t> exponent;
        if (m_key) {
            result.keyType = static_cast<int>(m_key->type());
            result.extractable = m_key->extractable();
            result.usages = m_key->usagesBitmap();
            auto metadata = m_key->algorithm();
            if (auto* rsa = std::get_if<CryptoRsaHashedKeyAlgorithm>(&metadata)) {
                result.modulusBits = rsa->modulusLength;
                result.hashBits = rsa->hash.name == "SHA-1"_s ? 1 : rsa->hash.name == "SHA-256"_s ? 256 : rsa->hash.name == "SHA-384"_s ? 384 : 512;
                exponent.append(rsa->publicExponent->span());
                result.exponent = bytes(exponent);
            }
            if (auto* ec = std::get_if<CryptoEcKeyAlgorithm>(&metadata))
                result.curve = ec->namedCurve == "P-256"_s ? 256 : ec->namedCurve == "P-384"_s ? 384 : 521;
        }
        if (!exception && (m_request.operation == 1 || m_request.operation == 2)) {
            result.firstKey = new KeyHandle { m_document.copyRef(), Ref<CryptoKey> { *m_key }, m_owner };
            if (m_second)
                result.secondKey = new KeyHandle { m_document.copyRef(), Ref<CryptoKey> { *m_second }, m_owner };
        }
        std::array<CString, 14> strings;
        result.jwkExt = -1;
        if (jwk) {
            for (size_t i = 0; i < fields.size(); ++i) {
                if (!(jwk->*fields[i]).isNull()) {
                    strings[i] = (jwk->*fields[i]).utf8();
                    result.jwk[i] = bytes(strings[i]);
                }
            }
            result.jwkExt = jwk->ext ? *jwk->ext : -1;
        }
        m_callback(m_context, &result);
    }
    void perform()
    {
        if (!owner() || !m_key) { fail(ExceptionCode::InvalidAccessError); return; }
        if (m_request.operation <= 2) { finish({ }); return; }
        if (m_request.operation == 3) {
            m_algorithm->exportKey(format(m_request.format), Ref<CryptoKey> { *m_key },
                [self = Ref { *this }](CryptoKeyFormat, KeyData&& data) {
                    if (auto* bytes = std::get_if<Vector<uint8_t>>(&data))
                        self->finish(*bytes);
                    else
                        self->finish({ }, std::nullopt, &std::get<JsonWebKey>(data));
                }, [self = Ref { *this }](ExceptionCode code) { self->fail(code); });
            return;
        }
        std::unique_ptr<CryptoAlgorithmParameters> parameters;
        if (m_request.algorithm == 2) {
            auto value = makeUnique<CryptoAlgorithmRsaPssParams>(m_algorithm->identifier());
            value->saltLength = m_request.parameter;
            parameters = WTF::move(value);
        } else if (m_request.algorithm == 3) {
            auto value = makeUnique<CryptoAlgorithmRsaOaepParams>(m_algorithm->identifier());
            value->label = BufferSource { m_label.span() };
            parameters = WTF::move(value);
        } else if (m_request.algorithm == 4) {
            auto value = makeUnique<CryptoAlgorithmEcdsaParams>(m_algorithm->identifier());
            value->hashIdentifier = hash(m_request.hash);
            parameters = WTF::move(value);
        } else if (m_request.algorithm == 5) {
            if (!m_peer) { fail(ExceptionCode::InvalidAccessError); return; }
            CryptoAlgorithmEcdhKeyDeriveParamsInit init { { }, Ref<CryptoKey> { *m_peer } };
            parameters = makeUnique<CryptoAlgorithmEcdhKeyDeriveParams>(m_algorithm->identifier(), WTF::move(init));
        } else
            parameters = makeUnique<CryptoAlgorithmParameters>(m_algorithm->identifier());
        auto vectorCallback = [self = Ref { *this }](const Vector<uint8_t>& output) {
            if (self->m_request.operation != 9) { self->finish(output); return; }
            self->m_algorithm = CryptoAlgorithmAESGCM::create();
            CryptoAlgorithmParameters params { self->m_algorithm->identifier() };
            self->m_algorithm->importKey(CryptoKeyFormat::Raw, KeyData { Vector<uint8_t> { output } }, params, true,
                CryptoKeyUsageEncrypt | CryptoKeyUsageDecrypt, [self = Ref { self.get() }](CryptoKey& key) {
                    self->m_key = &key;
                    ++self->m_borrowedRetains;
                    self->m_document->postTask([self = Ref { self.get() }](auto&) {
                        self->m_algorithm->exportKey(CryptoKeyFormat::Raw, Ref<CryptoKey> { *self->m_key },
                            [self = Ref { self.get() }](CryptoKeyFormat, KeyData&& result) { self->finish(std::get<Vector<uint8_t>>(result)); },
                            [self = Ref { self.get() }](ExceptionCode code) { self->fail(code); });
                    });
                }, [self = Ref { self.get() }](ExceptionCode code) { self->fail(code); });
        };
        auto failure = [self = Ref { *this }](ExceptionCode code) { self->fail(code); };
        switch (m_request.operation) {
        case 4: m_algorithm->sign(*parameters, Ref<CryptoKey> { *m_key }, Vector<uint8_t> { m_input }, WTF::move(vectorCallback), WTF::move(failure), m_document, m_queue); break;
        case 5: m_algorithm->doVerify(*parameters, Ref<CryptoKey> { *m_key }, Vector<uint8_t> { m_signature }, Vector<uint8_t> { m_input },
            [self = Ref { *this }](bool value) { self->finish({ }, std::nullopt, nullptr, value); }, WTF::move(failure), m_document, m_queue); break;
        case 6: m_algorithm->encrypt(*parameters, Ref<CryptoKey> { *m_key }, Vector<uint8_t> { m_input }, WTF::move(vectorCallback), WTF::move(failure), m_document, m_queue); break;
        case 7: m_algorithm->decrypt(*parameters, Ref<CryptoKey> { *m_key }, Vector<uint8_t> { m_input }, WTF::move(vectorCallback), WTF::move(failure), m_document, m_queue); break;
        case 8:
        case 9: m_algorithm->deriveBits(*parameters, Ref<CryptoKey> { *m_key }, m_request.parameter < 0 ? std::nullopt : std::optional<size_t>(m_request.parameter), WTF::move(vectorCallback), WTF::move(failure), m_document, m_queue); break;
        default: fail(ExceptionCode::NotSupportedError);
        }
    }
    Ref<Document> m_document;
    AsymmetricRequest m_request;
    RefPtr<CryptoAlgorithm> m_algorithm;
    AsymmetricCallback m_callback;
    void* m_context;
    std::thread::id m_owner;
    Ref<WorkQueue> m_queue;
    Vector<uint8_t> m_input, m_signature, m_label, m_exponent;
    JsonWebKey m_jwk;
    RefPtr<CryptoKey> m_key, m_peer, m_second;
    int m_terminalCount { 0 };
    int m_borrowedRetains { 0 };
    bool m_duringStart { false };
};
}

extern "C" WEBCORE_EXPORT int32_t ranvier_test_asymmetric_request_size() { return sizeof(AsymmetricRequest); }
extern "C" WEBCORE_EXPORT int32_t ranvier_test_asymmetric_result_size() { return sizeof(AsymmetricResult); }
extern "C" WEBCORE_EXPORT void* ranvier_test_asymmetric_start(RvNode* node, const AsymmetricRequest* request, AsymmetricCallback callback, void* context)
{
    if (!node || !request || request->size != sizeof(*request) || !callback)
        return nullptr;
    auto* document = dynamicDowncast<Document>(reinterpret_cast<Node*>(node));
    auto algorithm = implementation(request->algorithm);
    if (!document || !algorithm)
        return nullptr;
    auto valid = [](AsymmetricBytes value) { return value.length >= 0 && (!value.length || value.data); };
    for (auto value : { request->input, request->signature, request->label, request->exponent })
        if (!valid(value)) return nullptr;
    for (auto value : request->jwk)
        if (!valid(value)) return nullptr;
    for (auto* handle : { request->key, request->peer })
        if (handle && static_cast<KeyHandle*>(handle)->owner != std::this_thread::get_id()) return nullptr;
    auto operation = adoptRef(*new Operation(*document, *request, algorithm.releaseNonNull(), callback, context));
    operation->begin();
    return &operation.leakRef();
}
extern "C" WEBCORE_EXPORT int32_t ranvier_test_asymmetric_input(void* token, int32_t field, AsymmetricBytes* output)
{
    if (!token || !output) return -1;
    auto& operation = *static_cast<Operation*>(token);
    if (!operation.owner()) return -2;
    auto value = operation.input(field);
    if (!value) return -1;
    *output = *value;
    return 0;
}
extern "C" WEBCORE_EXPORT int32_t ranvier_test_asymmetric_barrier(void* token)
{
    if (!token) return -1;
    auto& operation = *static_cast<Operation*>(token);
    if (!operation.owner()) return -2;
    operation.barrier();
    return 0;
}
extern "C" WEBCORE_EXPORT int32_t ranvier_test_asymmetric_release(void* token)
{
    if (!token) return -1;
    auto& operation = *static_cast<Operation*>(token);
    if (!operation.owner()) return -2;
    operation.barrier();
    if (!operation.finished()) return -3;
    operation.deref();
    return 0;
}
extern "C" WEBCORE_EXPORT int32_t ranvier_test_asymmetric_key_release(void* token)
{
    if (!token) return -1;
    auto* handle = static_cast<KeyHandle*>(token);
    if (handle->owner != std::this_thread::get_id()) return -2;
    delete handle;
    return 0;
}

extern "C" WEBCORE_EXPORT int32_t ranvier_test_gcrypt_control_command(int32_t command)
{
#if USE(GCRYPT)
    switch (command) {
    case 0: return GCRYCTL_INITIALIZATION_FINISHED_P;
    case 1: return GCRYCTL_DISABLE_SECMEM;
    case 2: return GCRYCTL_INITIALIZATION_FINISHED;
    }
#endif
    return -1;
}

extern "C" WEBCORE_EXPORT int32_t ranvier_test_gcrypt_startup_import(int32_t requestedFormat)
{
    Vector<uint8_t> scalar { 0x77, 0x07, 0x6d, 0x0a, 0x73, 0x18, 0xa5, 0x7d,
        0x3c, 0x16, 0xc1, 0x72, 0x51, 0xb2, 0x66, 0x45, 0xdf, 0x4c, 0x2f, 0x87,
        0xeb, 0xc0, 0x99, 0x2a, 0xb1, 0x77, 0xfb, 0xa5, 0x1d, 0xb9, 0x2c, 0x2a };
    Vector<uint8_t> publicPoint { 0x85, 0x20, 0xf0, 0x09, 0x89, 0x30, 0xa7, 0x54,
        0x74, 0x8b, 0x7d, 0xdc, 0xb4, 0x3e, 0xf7, 0x5a, 0x0d, 0xbf, 0x3a, 0x0d,
        0x26, 0x38, 0x1a, 0xf4, 0xeb, 0xa4, 0xa9, 0x8e, 0xaa, 0x9b, 0x4e, 0x6a };
    auto algorithm = CryptoAlgorithmX25519::create();
    KeyData data;
    CryptoKeyFormat selectedFormat { CryptoKeyFormat::Jwk };
    if (requestedFormat == 1) {
        JsonWebKey jwk;
        jwk.kty = "OKP"_s;
        jwk.crv = "X25519"_s;
        jwk.x = base64URLEncodeToString(publicPoint.span());
        jwk.d = base64URLEncodeToString(scalar.span());
        data = WTF::move(jwk);
        selectedFormat = CryptoKeyFormat::Jwk;
    } else if (requestedFormat == 2) {
        Vector<uint8_t> der { 0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06,
            0x03, 0x2b, 0x65, 0x6e, 0x04, 0x22, 0x04, 0x20 };
        der.appendVector(scalar);
        data = WTF::move(der);
        selectedFormat = CryptoKeyFormat::Pkcs8;
    } else
        return -1000;
    RefPtr<CryptoKey> key;
    std::optional<ExceptionCode> error;
    int terminalCount { 0 };
    algorithm->importKey(selectedFormat, WTF::move(data), CryptoAlgorithmParameters { algorithm->identifier() }, true, CryptoKeyUsageDeriveBits,
        [&](CryptoKey& borrowed) { key = &borrowed; ++terminalCount; },
        [&](ExceptionCode value) { error = value; ++terminalCount; });
    if (terminalCount != 1)
        return -1001;
    if (error)
        return -static_cast<int32_t>(*error);
    if (!key || key->type() != CryptoKeyType::Private || key->algorithmIdentifier() != CryptoAlgorithmIdentifier::X25519
        || !key->extractable() || key->usagesBitmap() != CryptoKeyUsageDeriveBits)
        return -1002;
    return 0;
}
