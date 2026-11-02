#include "config.h"
#include "RanvierCryptoAsymmetricGlue.h"
#include "RanvierCryptoInternal.h"
#include "BufferSource.h"
#include "CryptoAlgorithmEcKeyParams.h"
#include "CryptoAlgorithmEcdhKeyDeriveParams.h"
#include "CryptoAlgorithmEcdsaParams.h"
#include "CryptoAlgorithmRegistry.h"
#include "CryptoAlgorithmRsaHashedImportParams.h"
#include "CryptoAlgorithmRsaHashedKeyGenParams.h"
#include "CryptoAlgorithmRsaOaepParams.h"
#include "CryptoAlgorithmRsaPssParams.h"
#include "CryptoAlgorithmX25519Params.h"
#include "CryptoKey.h"
#include "CryptoEcKeyAlgorithm.h"
#include "CryptoRsaHashedKeyAlgorithm.h"
#include "Document.h"
#include <limits>
#include <wtf/StdLibExtras.h>
#include <wtf/text/CString.h>

using namespace WebCore;
namespace Bridge = Ranvier::Crypto;

namespace {

bool flag(int32_t value) { return value == 0 || value == 1; }
bool valid(RanvierCryptoBytes value) { return value.length >= 0 && (!value.length || value.data); }
bool valid(const RanvierCryptoOptionalString& value) { return flag(value.present) && (!value.present || valid(value.value)); }
bool valid(RanvierCryptoStrings value)
{
    if (value.count < 0 || (value.count && !value.items))
        return false;
    for (int32_t index = 0; index < value.count; ++index) {
        if (!valid(value.items[index]))
            return false;
    }
    return true;
}

String text(RanvierCryptoBytes value)
{
    return String::fromUTF8(std::span { reinterpret_cast<const char*>(value.data), static_cast<size_t>(value.length) });
}

Vector<uint8_t> copy(RanvierCryptoBytes value)
{
    return Vector<uint8_t>(std::span { value.data, static_cast<size_t>(value.length) });
}

bool isRsa(CryptoAlgorithmIdentifier id)
{
    return id == CryptoAlgorithmIdentifier::RSASSA_PKCS1_v1_5 || id == CryptoAlgorithmIdentifier::RSA_PSS || id == CryptoAlgorithmIdentifier::RSA_OAEP;
}

bool isAsymmetric(CryptoAlgorithmIdentifier id)
{
    return isRsa(id) || id == CryptoAlgorithmIdentifier::ECDSA || id == CryptoAlgorithmIdentifier::ECDH
        || id == CryptoAlgorithmIdentifier::Ed25519 || id == CryptoAlgorithmIdentifier::X25519;
}

std::optional<CryptoAlgorithmIdentifier> identifier(RanvierCryptoBytes name)
{
    auto id = CryptoAlgorithmRegistry::singleton().identifier(text(name));
    return id && isAsymmetric(*id) ? id : std::nullopt;
}

std::optional<ExceptionCode> hashOf(const RanvierCryptoOptionalString& input, CryptoAlgorithmIdentifier& output)
{
    if (!input.present)
        return ExceptionCode::TypeError;
    auto id = CryptoAlgorithmRegistry::singleton().identifier(text(input.value));
    if (!id || (*id != CryptoAlgorithmIdentifier::SHA_1 && *id != CryptoAlgorithmIdentifier::SHA_256
        && *id != CryptoAlgorithmIdentifier::SHA_384 && *id != CryptoAlgorithmIdentifier::SHA_512))
        return ExceptionCode::NotSupportedError;
    output = *id;
    return std::nullopt;
}

int32_t begin(RvNode* handle, RanvierCryptoOperationHandle* output, Document*& document)
{
    if (!output)
        return RV_ERR_NULL_ARGUMENT;
    output->value = 0;
    return Bridge::documentOf(handle, document);
}

int32_t reject(uint64_t id, ExceptionCode error)
{
    Bridge::deliverError(id, error);
    return RV_OK;
}

auto onError(uint64_t id)
{
    return [id](ExceptionCode error) { Bridge::deliverError(id, error); };
}

std::optional<CryptoKeyFormat> formatOf(RanvierCryptoBytes input)
{
    auto name = text(input);
    if (name == "raw"_s) return CryptoKeyFormat::Raw;
    if (name == "jwk"_s) return CryptoKeyFormat::Jwk;
    if (name == "spki"_s) return CryptoKeyFormat::Spki;
    if (name == "pkcs8"_s) return CryptoKeyFormat::Pkcs8;
    return std::nullopt;
}

std::optional<ExceptionCode> generationParameters(const RanvierCryptoAsymmetricKeyParams& input, std::unique_ptr<CryptoAlgorithmParameters>& output)
{
    auto id = identifier(input.name);
    if (!id)
        return ExceptionCode::NotSupportedError;
    if (!isRsa(*id))
        return Bridge::normalizeAsymmetricImport(input, output);
    if (!input.modulus_length_present || !input.public_exponent_present || input.modulus_length_bits > UINT32_MAX)
        return ExceptionCode::TypeError;
    CryptoAlgorithmIdentifier hash;
    if (auto error = hashOf(input.hash, hash))
        return error;
    auto exponent = copy(input.public_exponent);
    CryptoAlgorithmRsaHashedKeyGenParamsInit init { { { }, static_cast<size_t>(input.modulus_length_bits), Uint8Array::create(ArrayBuffer::create(exponent.span())) }, { } };
    auto params = makeUnique<CryptoAlgorithmRsaHashedKeyGenParams>(*id, WTF::move(init), hash);
    params->hash = CryptoAlgorithmRegistry::singleton().name(hash);
    output = WTF::move(params);
    return std::nullopt;
}

bool valid(const RanvierCryptoAsymmetricSignParams* input)
{
    return input && input->size == sizeof(*input) && valid(input->name) && valid(input->hash) && flag(input->salt_length_present);
}

std::optional<ExceptionCode> signatureParameters(const RanvierCryptoAsymmetricSignParams& input, std::unique_ptr<CryptoAlgorithmParameters>& output)
{
    auto id = identifier(input.name);
    if (!id)
        return ExceptionCode::NotSupportedError;
    if (*id == CryptoAlgorithmIdentifier::RSA_PSS) {
        if (!input.salt_length_present || input.salt_length_bytes > UINT32_MAX)
            return ExceptionCode::TypeError;
        auto params = makeUnique<CryptoAlgorithmRsaPssParams>(*id);
        params->saltLength = static_cast<size_t>(input.salt_length_bytes);
        output = WTF::move(params);
    } else if (*id == CryptoAlgorithmIdentifier::ECDSA) {
        CryptoAlgorithmIdentifier hash;
        if (auto error = hashOf(input.hash, hash))
            return error;
        auto params = makeUnique<CryptoAlgorithmEcdsaParams>(*id);
        params->hash = CryptoAlgorithmRegistry::singleton().name(hash);
        params->hashIdentifier = hash;
        output = WTF::move(params);
    } else if (*id == CryptoAlgorithmIdentifier::RSASSA_PKCS1_v1_5 || *id == CryptoAlgorithmIdentifier::Ed25519)
        output = makeUnique<CryptoAlgorithmParameters>(*id);
    else
        return ExceptionCode::NotSupportedError;
    return std::nullopt;
}

int32_t startSignature(RvNode* handle, const RanvierCryptoAsymmetricSignParams* input, RanvierCryptoKeyHandle keyHandle,
    RanvierCryptoBytes data, const RanvierCryptoBytes* signature, RanvierCryptoOperationHandle* output)
{
    Document* document;
    if (auto status = begin(handle, output, document))
        return status;
    if (!valid(input) || !valid(data) || (signature && !valid(*signature)))
        return RV_ERR_NULL_ARGUMENT;
    RefPtr<CryptoKey> key;
    if (auto status = Bridge::lookupKey(keyHandle, key))
        return status;
    auto id = Bridge::admit(*document, output);
    std::unique_ptr<CryptoAlgorithmParameters> params;
    if (auto error = signatureParameters(*input, params))
        return reject(id, *error);
    auto usage = signature ? CryptoKeyUsageVerify : CryptoKeyUsageSign;
    auto type = signature ? CryptoKey::Type::Public : CryptoKey::Type::Private;
    if (key->algorithmIdentifier() != params->identifier || key->type() != type || !key->allows(usage))
        return reject(id, ExceptionCode::InvalidAccessError);
    auto algorithm = CryptoAlgorithmRegistry::singleton().create(params->identifier);
    if (!algorithm)
        return reject(id, ExceptionCode::NotSupportedError);
    if (signature)
        algorithm->doVerify(*params, key.releaseNonNull(), copy(*signature), copy(data), [id](bool result) { Bridge::deliverBoolean(id, result); }, onError(id), *document, Bridge::queue());
    else
        algorithm->sign(*params, key.releaseNonNull(), copy(data), [id](const Vector<uint8_t>& result) { Bridge::deliverBytes(id, result); }, onError(id), *document, Bridge::queue());
    return RV_OK;
}

int32_t startOaep(RvNode* handle, const RanvierCryptoAsymmetricOaepParams* input, RanvierCryptoKeyHandle keyHandle,
    RanvierCryptoBytes data, bool decrypting, RanvierCryptoOperationHandle* output)
{
    Document* document;
    if (auto status = begin(handle, output, document))
        return status;
    if (!Bridge::validAsymmetricOaepParams(input) || !valid(data))
        return RV_ERR_NULL_ARGUMENT;
    RefPtr<CryptoKey> key;
    if (auto status = Bridge::lookupKey(keyHandle, key))
        return status;
    auto id = Bridge::admit(*document, output);
    std::unique_ptr<CryptoAlgorithmParameters> params;
    if (auto error = Bridge::normalizeAsymmetricOaep(*input, params))
        return reject(id, *error);
    auto usage = decrypting ? CryptoKeyUsageDecrypt : CryptoKeyUsageEncrypt;
    auto type = decrypting ? CryptoKey::Type::Private : CryptoKey::Type::Public;
    if (key->algorithmIdentifier() != params->identifier || key->type() != type || !key->allows(usage))
        return reject(id, ExceptionCode::InvalidAccessError);
    auto algorithm = CryptoAlgorithmRegistry::singleton().create(params->identifier);
    if (!algorithm)
        return reject(id, ExceptionCode::NotSupportedError);
    auto complete = [id](const Vector<uint8_t>& result) { Bridge::deliverBytes(id, result); };
    if (decrypting)
        algorithm->decrypt(*params, key.releaseNonNull(), copy(data), WTF::move(complete), onError(id), *document, Bridge::queue());
    else
        algorithm->encrypt(*params, key.releaseNonNull(), copy(data), WTF::move(complete), onError(id), *document, Bridge::queue());
    return RV_OK;
}

bool valid(const RanvierCryptoAsymmetricDeriveParams* input)
{
    return input && input->size == sizeof(*input) && valid(input->name) && flag(input->public_key_present);
}

std::optional<ExceptionCode> derivationParameters(const RanvierCryptoAsymmetricDeriveParams& input, const RefPtr<CryptoKey>& peer,
    std::unique_ptr<CryptoAlgorithmParameters>& output)
{
    auto id = identifier(input.name);
    if (!id || (*id != CryptoAlgorithmIdentifier::ECDH && *id != CryptoAlgorithmIdentifier::X25519))
        return ExceptionCode::NotSupportedError;
    if (!input.public_key_present)
        return ExceptionCode::TypeError;
    if (*id == CryptoAlgorithmIdentifier::ECDH) {
        CryptoAlgorithmEcdhKeyDeriveParamsInit init { { }, Ref<CryptoKey> { *peer } };
        output = makeUnique<CryptoAlgorithmEcdhKeyDeriveParams>(*id, WTF::move(init));
    } else {
        CryptoAlgorithmX25519ParamsInit init { { }, Ref<CryptoKey> { *peer } };
        output = makeUnique<CryptoAlgorithmX25519Params>(*id, WTF::move(init));
    }
    return std::nullopt;
}

void derive(uint64_t id, const CryptoAlgorithmParameters& params, Ref<CryptoKey>&& key, std::optional<size_t> length, CryptoAlgorithm::VectorCallback&& complete)
{
    auto* document = Bridge::pendingDocument(id);
    if (!document)
        return;
    auto algorithm = CryptoAlgorithmRegistry::singleton().create(params.identifier);
    if (!algorithm) {
        Bridge::deliverError(id, ExceptionCode::NotSupportedError);
        return;
    }
    algorithm->deriveBits(params, WTF::move(key), length, WTF::move(complete), onError(id), *document, Bridge::queue());
}

int32_t copyMetadata(std::span<const uint8_t> data, uint8_t* output, int32_t capacity, int32_t* length)
{
    if (!length || capacity < 0 || (capacity && !output))
        return RV_ERR_NULL_ARGUMENT;
    *length = 0;
    if (data.size() > INT32_MAX)
        return RV_ERR_BUFFER_TOO_SMALL;
    *length = static_cast<int32_t>(data.size());
    if (static_cast<size_t>(capacity) < data.size())
        return RV_ERR_BUFFER_TOO_SMALL;
    if (!data.empty())
        memcpy(output, data.data(), data.size());
    return RV_OK;
}

}

namespace Ranvier::Crypto {

bool validAsymmetricKeyParams(const RanvierCryptoAsymmetricKeyParams* input)
{
    return input && input->size == sizeof(*input) && valid(input->name) && valid(input->hash) && valid(input->named_curve)
        && flag(input->modulus_length_present) && flag(input->public_exponent_present)
        && (!input->public_exponent_present || valid(input->public_exponent));
}

bool validAsymmetricOaepParams(const RanvierCryptoAsymmetricOaepParams* input)
{
    return input && input->size == sizeof(*input) && valid(input->name) && flag(input->label_present)
        && (!input->label_present || valid(input->label));
}

std::optional<ExceptionCode> normalizeAsymmetricImport(const RanvierCryptoAsymmetricKeyParams& input, std::unique_ptr<CryptoAlgorithmParameters>& output)
{
    auto id = identifier(input.name);
    if (!id)
        return ExceptionCode::NotSupportedError;
    if (isRsa(*id)) {
        CryptoAlgorithmIdentifier hash;
        if (auto error = hashOf(input.hash, hash))
            return error;
        auto params = makeUnique<CryptoAlgorithmRsaHashedImportParams>(*id);
        params->hash = CryptoAlgorithmRegistry::singleton().name(hash);
        params->hashIdentifier = hash;
        output = WTF::move(params);
    } else if (*id == CryptoAlgorithmIdentifier::ECDSA || *id == CryptoAlgorithmIdentifier::ECDH) {
        if (!input.named_curve.present)
            return ExceptionCode::TypeError;
        auto params = makeUnique<CryptoAlgorithmEcKeyParams>(*id);
        params->namedCurve = text(input.named_curve.value);
        output = WTF::move(params);
    } else
        output = makeUnique<CryptoAlgorithmParameters>(*id);
    return std::nullopt;
}

std::optional<ExceptionCode> normalizeAsymmetricOaep(const RanvierCryptoAsymmetricOaepParams& input, std::unique_ptr<CryptoAlgorithmParameters>& output)
{
    auto id = identifier(input.name);
    if (!id || *id != CryptoAlgorithmIdentifier::RSA_OAEP)
        return ExceptionCode::NotSupportedError;
    auto params = makeUnique<CryptoAlgorithmRsaOaepParams>(*id);
    if (input.label_present) {
        params->label = BufferSource { std::span { input.label.data, static_cast<size_t>(input.label.length) } };
        params->labelVector();
    }
    output = WTF::move(params);
    return std::nullopt;
}

void importAsymmetricKey(uint64_t id, CryptoKeyFormat format, KeyData&& data, const CryptoAlgorithmParameters& params,
    bool extractable, CryptoKeyUsageBitmap usages, bool duplicateKeyOps)
{
    auto wipe = [&] {
        if (auto* bytes = std::get_if<Vector<uint8_t>>(&data))
            secureZeroSpan(bytes->mutableSpan());
    };
    if (!pendingDocument(id)) {
        wipe();
        return;
    }
    if (!isAsymmetric(params.identifier) || (isRsa(params.identifier) && format == CryptoKeyFormat::Raw)) {
        wipe();
        deliverError(id, ExceptionCode::NotSupportedError);
        return;
    }
    auto* jwk = std::get_if<JsonWebKey>(&data);
    if ((format == CryptoKeyFormat::Jwk) != !!jwk) {
        wipe();
        deliverError(id, ExceptionCode::TypeError);
        return;
    }
    bool privateKey = format == CryptoKeyFormat::Pkcs8 || (jwk && !jwk->d.isNull());
    CryptoKeyUsageBitmap allowed = 0;
    if (params.identifier == CryptoAlgorithmIdentifier::ECDH || params.identifier == CryptoAlgorithmIdentifier::X25519)
        allowed = privateKey ? CryptoKeyUsageDeriveKey | CryptoKeyUsageDeriveBits : 0;
    else if (params.identifier == CryptoAlgorithmIdentifier::RSA_OAEP)
        allowed = privateKey ? CryptoKeyUsageDecrypt | CryptoKeyUsageUnwrapKey : CryptoKeyUsageEncrypt | CryptoKeyUsageWrapKey;
    else
        allowed = privateKey ? CryptoKeyUsageSign : CryptoKeyUsageVerify;
    if (usages & ~allowed) {
        wipe();
        deliverError(id, ExceptionCode::SyntaxError);
        return;
    }
    if (jwk && duplicateKeyOps) {
        deliverError(id, ExceptionCode::DataError);
        return;
    }
    auto algorithm = CryptoAlgorithmRegistry::singleton().create(params.identifier);
    if (!algorithm) {
        wipe();
        deliverError(id, ExceptionCode::NotSupportedError);
        return;
    }
    algorithm->importKey(format, WTF::move(data), params, extractable, usages, [id](CryptoKey& key) { deliverKey(id, key); }, onError(id));
    wipe();
}

}

int32_t ranvier_crypto_asymmetric_supported(RvNode* handle, RanvierCryptoBytes name, int32_t* supported)
{
    if (!supported)
        return RV_ERR_NULL_ARGUMENT;
    *supported = 0;
    Document* document;
    if (auto status = Bridge::documentOf(handle, document))
        return status;
    if (!valid(name))
        return RV_ERR_NULL_ARGUMENT;
    if (auto id = identifier(name))
        *supported = !!CryptoAlgorithmRegistry::singleton().create(*id);
    return RV_OK;
}

int32_t ranvier_crypto_asymmetric_generate(RvNode* handle, const RanvierCryptoAsymmetricKeyParams* input, int32_t extractable,
    RanvierCryptoStrings requestedUsages, RanvierCryptoOperationHandle* output)
{
    Document* document;
    if (auto status = begin(handle, output, document))
        return status;
    if (!Bridge::validAsymmetricKeyParams(input) || !flag(extractable) || !valid(requestedUsages))
        return RV_ERR_NULL_ARGUMENT;
    auto id = Bridge::admit(*document, output);
    std::unique_ptr<CryptoAlgorithmParameters> params;
    if (auto error = generationParameters(*input, params))
        return reject(id, *error);
    CryptoKeyUsageBitmap usages;
    if (auto error = Bridge::normalizeUsages(requestedUsages, usages))
        return reject(id, *error);
    auto algorithm = CryptoAlgorithmRegistry::singleton().create(params->identifier);
    if (!algorithm)
        return reject(id, ExceptionCode::NotSupportedError);
    algorithm->generateKey(*params, extractable, usages, [id](KeyOrKeyPair&& result) {
        auto* pair = std::get_if<CryptoKeyPair>(&result);
        if (!pair || !pair->publicKey || !pair->privateKey)
            Bridge::deliverError(id, ExceptionCode::OperationError);
        else
            Bridge::deliverKeyPair(id, *pair->publicKey, *pair->privateKey);
    }, onError(id), *document);
    return RV_OK;
}

int32_t ranvier_crypto_asymmetric_import(RvNode* handle, RanvierCryptoBytes formatName, const RanvierCryptoAsymmetricKeyData* input,
    const RanvierCryptoAsymmetricKeyParams* options, int32_t extractable, RanvierCryptoStrings requestedUsages, RanvierCryptoOperationHandle* output)
{
    Document* document;
    if (auto status = begin(handle, output, document))
        return status;
    if (!valid(formatName) || !input || input->size != sizeof(*input) || !flag(input->raw_present)
        || (input->raw_present && !valid(input->raw)) || (input->jwk && !Bridge::validJwk(input->jwk))
        || !Bridge::validAsymmetricKeyParams(options) || !flag(extractable) || !valid(requestedUsages))
        return RV_ERR_NULL_ARGUMENT;
    auto id = Bridge::admit(*document, output);
    auto format = formatOf(formatName);
    if (!format)
        return reject(id, ExceptionCode::TypeError);
    std::unique_ptr<CryptoAlgorithmParameters> params;
    if (auto error = Bridge::normalizeAsymmetricImport(*options, params))
        return reject(id, *error);
    CryptoKeyUsageBitmap usages;
    if (auto error = Bridge::normalizeUsages(requestedUsages, usages))
        return reject(id, *error);
    if ((*format == CryptoKeyFormat::Jwk && (!input->jwk || input->raw_present))
        || (*format != CryptoKeyFormat::Jwk && (!input->raw_present || input->jwk)))
        return reject(id, ExceptionCode::TypeError);
    JsonWebKey jwk;
    bool duplicateKeyOps = false;
    if (input->jwk) {
        if (auto error = Bridge::copyJwk(*input->jwk, jwk, duplicateKeyOps))
            return reject(id, *error);
    }
    KeyData data = *format == CryptoKeyFormat::Jwk ? KeyData { WTF::move(jwk) } : KeyData { copy(input->raw) };
    Bridge::importAsymmetricKey(id, *format, WTF::move(data), *params, extractable, usages, duplicateKeyOps);
    return RV_OK;
}

int32_t ranvier_crypto_asymmetric_sign(RvNode* handle, const RanvierCryptoAsymmetricSignParams* params, RanvierCryptoKeyHandle key, RanvierCryptoBytes data, RanvierCryptoOperationHandle* output)
{
    return startSignature(handle, params, key, data, nullptr, output);
}

int32_t ranvier_crypto_asymmetric_verify(RvNode* handle, const RanvierCryptoAsymmetricSignParams* params, RanvierCryptoKeyHandle key, RanvierCryptoBytes signature, RanvierCryptoBytes data, RanvierCryptoOperationHandle* output)
{
    return startSignature(handle, params, key, data, &signature, output);
}

int32_t ranvier_crypto_asymmetric_encrypt(RvNode* handle, const RanvierCryptoAsymmetricOaepParams* params, RanvierCryptoKeyHandle key, RanvierCryptoBytes data, RanvierCryptoOperationHandle* output)
{
    return startOaep(handle, params, key, data, false, output);
}

int32_t ranvier_crypto_asymmetric_decrypt(RvNode* handle, const RanvierCryptoAsymmetricOaepParams* params, RanvierCryptoKeyHandle key, RanvierCryptoBytes data, RanvierCryptoOperationHandle* output)
{
    return startOaep(handle, params, key, data, true, output);
}

int32_t ranvier_crypto_asymmetric_derive_bits(RvNode* handle, const RanvierCryptoAsymmetricDeriveParams* input,
    RanvierCryptoKeyHandle baseHandle, RanvierCryptoOptionalLength requestedLength, RanvierCryptoOperationHandle* output)
{
    Document* document;
    if (auto status = begin(handle, output, document))
        return status;
    if (!valid(input) || !flag(requestedLength.present))
        return RV_ERR_NULL_ARGUMENT;
    RefPtr<CryptoKey> base, peer;
    if (auto status = Bridge::lookupKey(baseHandle, base))
        return status;
    if (input->public_key_present) {
        if (auto status = Bridge::lookupKey(input->public_key, peer))
            return status;
    }
    auto id = Bridge::admit(*document, output);
    if (requestedLength.present && requestedLength.bits > UINT32_MAX)
        return reject(id, ExceptionCode::TypeError);
    std::unique_ptr<CryptoAlgorithmParameters> params;
    if (auto error = derivationParameters(*input, peer, params))
        return reject(id, *error);
    if (base->algorithmIdentifier() != params->identifier || !base->allows(CryptoKeyUsageDeriveBits))
        return reject(id, ExceptionCode::InvalidAccessError);
    std::optional<size_t> length;
    if (requestedLength.present)
        length = static_cast<size_t>(requestedLength.bits);
    derive(id, *params, base.releaseNonNull(), length, [id](const Vector<uint8_t>& result) { Bridge::deliverBytes(id, result); });
    return RV_OK;
}

int32_t ranvier_crypto_asymmetric_derive_key(RvNode* handle, const RanvierCryptoAsymmetricDeriveParams* input,
    RanvierCryptoKeyHandle baseHandle, const RanvierCryptoDerivedKeyParams* target, int32_t extractable,
    RanvierCryptoStrings requestedUsages, RanvierCryptoOperationHandle* output)
{
    Document* document;
    if (auto status = begin(handle, output, document))
        return status;
    if (!valid(input) || !Bridge::validDerivedTarget(target) || !flag(extractable) || !valid(requestedUsages))
        return RV_ERR_NULL_ARGUMENT;
    RefPtr<CryptoKey> base, peer;
    if (auto status = Bridge::lookupKey(baseHandle, base))
        return status;
    if (input->public_key_present) {
        if (auto status = Bridge::lookupKey(input->public_key, peer))
            return status;
    }
    auto id = Bridge::admit(*document, output);
    std::unique_ptr<CryptoAlgorithmParameters> params;
    if (auto error = derivationParameters(*input, peer, params))
        return reject(id, *error);
    std::shared_ptr<Bridge::DerivedKeyTarget> normalized;
    if (auto error = Bridge::normalizeDerivedTarget(*target, extractable, requestedUsages, normalized))
        return reject(id, *error);
    if (base->algorithmIdentifier() != params->identifier || !base->allows(CryptoKeyUsageDeriveKey))
        return reject(id, ExceptionCode::InvalidAccessError);
    auto length = Bridge::derivedTargetLength(*normalized);
    if (length.hasException())
        return reject(id, length.releaseException().code());
    derive(id, *params, base.releaseNonNull(), length.releaseReturnValue(), [id, normalized](const Vector<uint8_t>& bytes) {
        Bridge::importDerivedKey(id, normalized, Vector<uint8_t>(bytes));
    });
    return RV_OK;
}

int32_t ranvier_crypto_asymmetric_key_info(RanvierCryptoKeyHandle handle, RanvierCryptoAsymmetricKeyInfo* info)
{
    if (!info || info->size != sizeof(*info))
        return RV_ERR_NULL_ARGUMENT;
    *info = { sizeof(*info), 0, 0, 0, 0 };
    RefPtr<CryptoKey> key;
    if (auto status = Bridge::lookupKey(handle, key))
        return status;
    if (!isAsymmetric(key->algorithmIdentifier()))
        return RV_ERR_WRONG_INTERFACE;
    auto metadata = key->algorithm();
    if (auto* rsa = std::get_if<CryptoRsaHashedKeyAlgorithm>(&metadata)) {
        info->modulus_length_present = 1;
        info->modulus_length_bits = rsa->modulusLength;
        info->hash_present = 1;
    } else if (std::holds_alternative<CryptoEcKeyAlgorithm>(metadata))
        info->named_curve_present = 1;
    return RV_OK;
}

int32_t ranvier_crypto_asymmetric_key_hash(RanvierCryptoKeyHandle handle, char* output, int32_t capacity, int32_t* length)
{
    RefPtr<CryptoKey> key;
    if (auto status = Bridge::lookupKey(handle, key))
        return status;
    auto metadata = key->algorithm();
    auto* rsa = std::get_if<CryptoRsaHashedKeyAlgorithm>(&metadata);
    if (!rsa)
        return RV_ERR_WRONG_INTERFACE;
    auto hash = rsa->hash.name.utf8();
    return copyMetadata(std::span { reinterpret_cast<const uint8_t*>(hash.data()), hash.length() }, reinterpret_cast<uint8_t*>(output), capacity, length);
}

int32_t ranvier_crypto_asymmetric_key_named_curve(RanvierCryptoKeyHandle handle, char* output, int32_t capacity, int32_t* length)
{
    RefPtr<CryptoKey> key;
    if (auto status = Bridge::lookupKey(handle, key))
        return status;
    auto metadata = key->algorithm();
    auto* ec = std::get_if<CryptoEcKeyAlgorithm>(&metadata);
    if (!ec)
        return RV_ERR_WRONG_INTERFACE;
    auto curve = ec->namedCurve.utf8();
    return copyMetadata(std::span { reinterpret_cast<const uint8_t*>(curve.data()), curve.length() }, reinterpret_cast<uint8_t*>(output), capacity, length);
}

int32_t ranvier_crypto_asymmetric_key_public_exponent(RanvierCryptoKeyHandle handle, uint8_t* output, int32_t capacity, int32_t* length)
{
    RefPtr<CryptoKey> key;
    if (auto status = Bridge::lookupKey(handle, key))
        return status;
    auto metadata = key->algorithm();
    auto* rsa = std::get_if<CryptoRsaHashedKeyAlgorithm>(&metadata);
    if (!rsa)
        return RV_ERR_WRONG_INTERFACE;
    return copyMetadata(rsa->publicExponent->span(), output, capacity, length);
}
