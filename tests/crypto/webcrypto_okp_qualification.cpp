#include "config.h"
#include "CryptoAlgorithmRegistry.h"
#include "CryptoAlgorithm.h"
#include "CryptoAlgorithmParameters.h"
#include "CryptoAlgorithmX25519Params.h"
#include "CryptoKeyOKP.h"
#include "CryptoKeyPair.h"
#include "Document.h"
#include "ExceptionCode.h"
#include "ExceptionOr.h"
#include "JsonWebKey.h"
#include "Node.h"
#include <WebCore/PlatformExportMacros.h>
#include <wtf/MainThread.h>
#include <wtf/NeverDestroyed.h>
#include <wtf/StdLibExtras.h>
#include <wtf/TypeCasts.h>
#include <wtf/WorkQueue.h>
#include <algorithm>
#include <memory>
#include <string_view>

using namespace WebCore;

namespace {

struct Outcome {
    bool done { false };
    std::optional<ExceptionCode> error;
    RefPtr<CryptoKey> key;
    std::optional<CryptoKeyPair> pair;
    std::optional<KeyData> data;
};

auto importKey(CryptoAlgorithm& algorithm, CryptoKeyFormat format, KeyData&& data, bool extractable, CryptoKeyUsageBitmap usages)
{
    auto result = std::make_shared<Outcome>();
    algorithm.importKey(format, WTF::move(data), CryptoAlgorithmParameters(algorithm.identifier()), extractable, usages,
        [result](CryptoKey& key) { result->key = &key; result->done = true; },
        [result](ExceptionCode code) { result->error = code; result->done = true; });
    return result;
}

auto exportKey(CryptoAlgorithm& algorithm, CryptoKeyFormat format, CryptoKey& key)
{
    auto result = std::make_shared<Outcome>();
    algorithm.exportKey(format, Ref<CryptoKey>(key),
        [result](CryptoKeyFormat, KeyData&& data) { result->data.emplace(WTF::move(data)); result->done = true; },
        [result](ExceptionCode code) { result->error = code; result->done = true; });
    return result;
}

Vector<uint8_t> decodeHex(std::string_view value)
{
    auto digit = [](char c) -> uint8_t { return c <= '9' ? c - '0' : c - 'a' + 10; };
    Vector<uint8_t> result;
    for (size_t i = 0; i < value.size(); i += 2)
        result.append(static_cast<uint8_t>((digit(value[i]) << 4) | digit(value[i + 1])));
    return result;
}

Vector<uint8_t> fixtureZeroBytes(size_t size)
{
    Vector<uint8_t> result(size);
    std::fill(result.begin(), result.end(), uint8_t { 0 });
    return result;
}

auto rfcPrivate(CryptoAlgorithm& algorithm, std::string_view seed)
{
    auto identifier = algorithm.identifier();
    Vector<uint8_t> encoded { 0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65,
        static_cast<uint8_t>(identifier == CryptoAlgorithmIdentifier::Ed25519 ? 0x70 : 0x6e), 0x04, 0x22, 0x04, 0x20 };
    encoded.appendVector(decodeHex(seed));
    return importKey(algorithm, CryptoKeyFormat::Pkcs8, WTF::move(encoded), true,
        identifier == CryptoAlgorithmIdentifier::Ed25519 ? CryptoKeyUsageSign : CryptoKeyUsageDeriveBits);
}

constexpr auto edSeed = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60";
constexpr auto edPublic = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a";
constexpr auto edSignature = "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b";
constexpr auto aliceSeed = "77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a";
constexpr auto alicePublic = "8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a";
constexpr auto bobSeed = "5dab087e624a8a4b79e17f8b83800ee66f3bb1292618b6fd1c2f8b27ff88e0eb";
constexpr auto bobPublic = "de9edb7d7b7dc1b4d35b61c2ece435373f8343c85b78674dadfc7e146f882b4f";

struct Job {
    uint64_t generation { 0 };
    int32_t status { 0 };
    std::optional<ExceptionCode> error;
    Vector<uint8_t> bytes;
    bool boolean { false };
};

Job& job()
{
    static NeverDestroyed<Job> value;
    return value.get();
}

WorkQueue& queue()
{
    static NeverDestroyed<Ref<WorkQueue>> value(WorkQueue::create("org.ranvier.TestOKP"_s));
    return value.get().get();
}

} // namespace

#define EXPECT_PORT(condition) do { ++assertions; if (!(condition)) return -assertions; } while (false)

extern "C" WEBCORE_EXPORT int32_t ranvier_test_okp_key_ports(void* documentHandle)
{
    int32_t assertions = 0;
    auto* document = dynamicDowncast<Document>(reinterpret_cast<Node*>(documentHandle));
    EXPECT_PORT(isMainThread() && document && document->isFullyActive());
    for (auto curve : { CryptoKeyOKP::NamedCurve::Ed25519, CryptoKeyOKP::NamedCurve::X25519 }) {
        bool ed = curve == CryptoKeyOKP::NamedCurve::Ed25519;
        auto identifier = ed ? CryptoAlgorithmIdentifier::Ed25519 : CryptoAlgorithmIdentifier::X25519;
        auto publicUsages = ed ? CryptoKeyUsageVerify : 0;
        auto privateUsages = ed ? CryptoKeyUsageSign : CryptoKeyUsageDeriveBits;
        auto algorithm = CryptoAlgorithmRegistry::singleton().create(identifier);
        EXPECT_PORT(algorithm);
        Vector<uint8_t> previous;
        for (unsigned iteration = 0; iteration < 8; ++iteration) {
            auto generated = std::make_shared<Outcome>();
            auto usages = privateUsages | publicUsages;
            algorithm->generateKey(CryptoAlgorithmParameters(identifier), iteration % 2, usages,
                [generated](KeyOrKeyPair&& value) { generated->pair.emplace(std::get<CryptoKeyPair>(WTF::move(value))); generated->done = true; },
                [generated](ExceptionCode code) { generated->error = code; generated->done = true; }, *document);
            EXPECT_PORT(generated->done && !generated->error && generated->pair);
            auto pair = WTF::move(*generated->pair);
            EXPECT_PORT(pair.publicKey && pair.privateKey);
            auto& publicKey = downcast<CryptoKeyOKP>(*pair.publicKey);
            auto& privateKey = downcast<CryptoKeyOKP>(*pair.privateKey);
            EXPECT_PORT(publicKey.type() == CryptoKeyType::Public && privateKey.type() == CryptoKeyType::Private);
            EXPECT_PORT(publicKey.extractable() && privateKey.extractable() == static_cast<bool>(iteration % 2));
            EXPECT_PORT(publicKey.usagesBitmap() == publicUsages && privateKey.usagesBitmap() == privateUsages);
            EXPECT_PORT(publicKey.algorithmIdentifier() == identifier && privateKey.algorithmIdentifier() == identifier);
            EXPECT_PORT(publicKey.namedCurve() == curve && privateKey.namedCurve() == curve);
            EXPECT_PORT(publicKey.keySizeInBytes() == 32 && privateKey.keySizeInBytes() == 32);

            auto rawResult = publicKey.exportRaw();
            EXPECT_PORT(!rawResult.hasException());
            auto raw = rawResult.releaseReturnValue();
            EXPECT_PORT(raw.size() == 32 && raw != previous);
            previous = raw;
            EXPECT_PORT(privateKey.exportRaw().hasException());
            auto importedRaw = CryptoKeyOKP::importRaw(identifier, curve, Vector<uint8_t>(raw), true, publicUsages);
            EXPECT_PORT(importedRaw && importedRaw->platformKey() == publicKey.platformKey());
            EXPECT_PORT(!CryptoKeyOKP::importRaw(identifier, curve, fixtureZeroBytes(31), true, publicUsages));
            EXPECT_PORT(!CryptoKeyOKP::importRaw(identifier, curve, fixtureZeroBytes(33), true, publicUsages));
            auto rawImported = importKey(*algorithm, CryptoKeyFormat::Raw, Vector<uint8_t>(raw), true, publicUsages);
            EXPECT_PORT(rawImported->done && rawImported->key && rawImported->key->type() == CryptoKeyType::Public);
            auto genericRaw = exportKey(*algorithm, CryptoKeyFormat::Raw, publicKey);
            EXPECT_PORT(genericRaw->done && genericRaw->data && std::get<Vector<uint8_t>>(*genericRaw->data) == raw);
            auto rawBadUsage = importKey(*algorithm, CryptoKeyFormat::Raw, Vector<uint8_t>(raw), true, privateUsages);
            EXPECT_PORT(rawBadUsage->done && rawBadUsage->error == ExceptionCode::SyntaxError && !rawBadUsage->key);
            auto rawBadLength = importKey(*algorithm, CryptoKeyFormat::Raw, fixtureZeroBytes(31), true, publicUsages);
            EXPECT_PORT(rawBadLength->done && rawBadLength->error == ExceptionCode::DataError && !rawBadLength->key);

            auto spkiResult = publicKey.exportSpki();
            auto pkcs8Result = privateKey.exportPkcs8();
            EXPECT_PORT(!spkiResult.hasException() && !pkcs8Result.hasException());
            auto spki = spkiResult.releaseReturnValue();
            auto pkcs8 = pkcs8Result.releaseReturnValue();
            EXPECT_PORT(spki.size() == 44 && pkcs8.size() == 48);
            auto importedPublic = CryptoKeyOKP::importSpki(identifier, curve, Vector<uint8_t>(spki), true, publicUsages);
            auto importedPrivate = CryptoKeyOKP::importPkcs8(identifier, curve, Vector<uint8_t>(pkcs8), false, privateUsages);
            EXPECT_PORT(importedPublic && importedPrivate);
            EXPECT_PORT(importedPublic->platformKey() == publicKey.platformKey());
            EXPECT_PORT(importedPrivate->platformKey() == privateKey.platformKey() && !importedPrivate->extractable());
            auto genericSpki = exportKey(*algorithm, CryptoKeyFormat::Spki, publicKey);
            auto genericPkcs8 = exportKey(*algorithm, CryptoKeyFormat::Pkcs8, privateKey);
            EXPECT_PORT(genericSpki->done && genericPkcs8->done && genericSpki->data && genericPkcs8->data);
            EXPECT_PORT(std::get<Vector<uint8_t>>(*genericSpki->data) == spki && std::get<Vector<uint8_t>>(*genericPkcs8->data) == pkcs8);
            auto genericPrivate = importKey(*algorithm, CryptoKeyFormat::Pkcs8, Vector<uint8_t>(pkcs8), false, privateUsages);
            EXPECT_PORT(genericPrivate->done && genericPrivate->key && !genericPrivate->key->extractable());
            auto genericPublic = importKey(*algorithm, CryptoKeyFormat::Spki, Vector<uint8_t>(spki), true, publicUsages);
            EXPECT_PORT(genericPublic->done && genericPublic->key && genericPublic->key->type() == CryptoKeyType::Public);
            auto privateRaw = exportKey(*algorithm, CryptoKeyFormat::Raw, privateKey);
            EXPECT_PORT(privateRaw->done && privateRaw->error == ExceptionCode::InvalidAccessError);
            EXPECT_PORT(privateKey.exportSpki().hasException() && publicKey.exportPkcs8().hasException());
            auto trailingSpki = spki;
            trailingSpki.append(0);
            EXPECT_PORT(!CryptoKeyOKP::importSpki(identifier, curve, WTF::move(trailingSpki), true, publicUsages));
            auto trailingPkcs8 = pkcs8;
            trailingPkcs8.append(0);
            EXPECT_PORT(!CryptoKeyOKP::importPkcs8(identifier, curve, WTF::move(trailingPkcs8), true, privateUsages));
            auto wrongSpki = spki;
            wrongSpki[8] = ed ? 0x6e : 0x70;
            EXPECT_PORT(!CryptoKeyOKP::importSpki(identifier, curve, WTF::move(wrongSpki), true, publicUsages));
            auto wrongVersion = pkcs8;
            wrongVersion[4] = 1;
            EXPECT_PORT(!CryptoKeyOKP::importPkcs8(identifier, curve, WTF::move(wrongVersion), true, privateUsages));
            Vector<uint8_t> nullParameters { 0x30, 0x2c, 0x30, 0x07, 0x06, 0x03, 0x2b, 0x65,
                static_cast<uint8_t>(ed ? 0x70 : 0x6e), 0x05, 0x00, 0x03, 0x21, 0x00 };
            nullParameters.appendVector(raw);
            EXPECT_PORT(!CryptoKeyOKP::importSpki(identifier, curve, WTF::move(nullParameters), true, publicUsages));
            auto nonzeroUnusedBits = spki;
            nonzeroUnusedBits[11] = 1;
            nonzeroUnusedBits.last() &= 0xfe;
            EXPECT_PORT(!CryptoKeyOKP::importSpki(identifier, curve, WTF::move(nonzeroUnusedBits), true, publicUsages));

            auto publicJwkResult = publicKey.exportJwk();
            auto privateJwkResult = privateKey.exportJwk();
            EXPECT_PORT(!publicJwkResult.hasException() && !privateJwkResult.hasException());
            auto publicJwk = publicJwkResult.releaseReturnValue();
            auto privateJwk = privateJwkResult.releaseReturnValue();
            EXPECT_PORT(publicJwk.d.isNull() && !privateJwk.d.isEmpty() && publicJwk.x == privateJwk.x);
            publicJwk.key_ops = std::nullopt;
            privateJwk.key_ops = std::nullopt;
            if (ed) {
                publicJwk.use = "sig"_s;
                privateJwk.use = "sig"_s;
            }
            auto jwkPublic = CryptoKeyOKP::importJwk(identifier, curve, JsonWebKey(publicJwk), true, publicUsages);
            auto jwkPrivate = CryptoKeyOKP::importJwk(identifier, curve, JsonWebKey(privateJwk), false, privateUsages);
            EXPECT_PORT(jwkPublic && jwkPrivate);
            EXPECT_PORT(jwkPublic->platformKey() == publicKey.platformKey() && jwkPrivate->platformKey() == privateKey.platformKey());
            auto genericJwk = exportKey(*algorithm, CryptoKeyFormat::Jwk, privateKey);
            EXPECT_PORT(genericJwk->done && genericJwk->data && std::get<JsonWebKey>(*genericJwk->data).d == privateJwk.d);
            auto genericJwkData = privateJwk;
            if (!ed)
                genericJwkData.use = "enc"_s;
            auto genericJwkImport = importKey(*algorithm, CryptoKeyFormat::Jwk, WTF::move(genericJwkData), false, privateUsages);
            EXPECT_PORT(genericJwkImport->done && genericJwkImport->key && !genericJwkImport->error);
            auto wrongPair = privateJwk;
            wrongPair.x = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"_s;
            EXPECT_PORT(!CryptoKeyOKP::importJwk(identifier, curve, WTF::move(wrongPair), false, privateUsages));
            auto wrongCurve = privateJwk;
            wrongCurve.crv = ed ? "X25519"_s : "Ed25519"_s;
            EXPECT_PORT(!CryptoKeyOKP::importJwk(identifier, curve, WTF::move(wrongCurve), false, privateUsages));
            if (ed) {
                publicJwk.use = "sign"_s;
                EXPECT_PORT(!CryptoKeyOKP::importJwk(identifier, curve, WTF::move(publicJwk), true, publicUsages));
            }
        }
    }
    return assertions;
}

extern "C" WEBCORE_EXPORT int32_t ranvier_test_okp_begin(void* documentHandle, int32_t scenario)
{
    if (!isMainThread() || !documentHandle || scenario < 0 || scenario > 23)
        return -1;
    auto* document = dynamicDowncast<Document>(reinterpret_cast<Node*>(documentHandle));
    if (!document || !document->isFullyActive())
        return -2;
    auto& state = job();
    ++state.generation;
    state.status = 0;
    state.error = std::nullopt;
    secureZeroSpan(state.bytes.mutableSpan());
    state.bytes.clear();
    state.boolean = false;
    auto generation = state.generation;
    auto bytes = [generation](const Vector<uint8_t>& value) { if (job().generation == generation) { job().bytes = value; job().status = 1; } };
    auto boolean = [generation](bool value) { if (job().generation == generation) { job().boolean = value; job().status = 1; } };
    auto error = [generation](ExceptionCode value) { if (job().generation == generation) { job().error = value; job().status = 2; } };
    bool ed = scenario < 8;
    auto algorithm = CryptoAlgorithmRegistry::singleton().create(ed ? CryptoAlgorithmIdentifier::Ed25519 : CryptoAlgorithmIdentifier::X25519);
    if (!algorithm)
        return -3;
    if (ed) {
        auto privateKey = rfcPrivate(*algorithm, edSeed)->key;
        auto publicData = scenario == 4 ? decodeHex("0000000000000000000000000000000000000000000000000000000000000000") : decodeHex(edPublic);
        auto publicKey = importKey(*algorithm, CryptoKeyFormat::Raw, WTF::move(publicData), true, CryptoKeyUsageVerify)->key;
        if (!privateKey || !publicKey)
            return -4;
        if (!scenario || scenario == 6) {
            RefPtr<CryptoKey> key = scenario == 6 ? publicKey : privateKey;
            algorithm->sign(CryptoAlgorithmParameters(algorithm->identifier()), key.releaseNonNull(), { }, WTF::move(bytes), WTF::move(error), *document, queue());
        } else {
            auto signature = decodeHex(edSignature);
            if (scenario == 2)
                signature[0] ^= 1;
            if (scenario == 3)
                signature.shrink(63);
            if (scenario == 5)
                std::fill(signature.begin(), signature.begin() + 32, 0);
            RefPtr<CryptoKey> key = scenario == 7 ? privateKey : publicKey;
            algorithm->doVerify(CryptoAlgorithmParameters(algorithm->identifier()), key.releaseNonNull(), WTF::move(signature), { }, WTF::move(boolean), WTF::move(error), *document, queue());
        }
    } else {
        auto privateKey = rfcPrivate(*algorithm, scenario == 9 ? bobSeed : aliceSeed)->key;
        auto publicData = (scenario == 10 || scenario == 18 || scenario == 19 || scenario == 23) ? decodeHex("0000000000000000000000000000000000000000000000000000000000000000") : decodeHex(scenario == 9 ? alicePublic : bobPublic);
        auto publicKey = importKey(*algorithm, CryptoKeyFormat::Raw, WTF::move(publicData), true, 0)->key;
        if (!privateKey || !publicKey)
            return -5;
        CryptoAlgorithmX25519ParamsInit init { { }, Ref<CryptoKey>(*(scenario == 11 ? privateKey : publicKey)) };
        if (scenario == 13) {
            auto edAlgorithm = CryptoAlgorithmRegistry::singleton().create(CryptoAlgorithmIdentifier::Ed25519);
            auto edKey = importKey(*edAlgorithm, CryptoKeyFormat::Raw, decodeHex(edPublic), true, CryptoKeyUsageVerify)->key;
            init.publicKey = edKey.releaseNonNull();
        }
        CryptoAlgorithmX25519Params parameters(CryptoAlgorithmIdentifier::X25519, WTF::move(init));
        std::optional<size_t> length = scenario == 14 ? 264 : scenario == 15 ? 128 : (scenario == 16 || scenario == 19) ? 0 : 256;
        if (scenario >= 20)
            length = (scenario == 20 || scenario == 23) ? 1 : scenario == 21 ? 7 : 9;
        if (scenario == 17 || scenario == 18)
            length = std::nullopt;
        RefPtr<CryptoKey> baseKey = scenario == 12 ? publicKey : privateKey;
        algorithm->deriveBits(parameters, baseKey.releaseNonNull(), length, WTF::move(bytes), WTF::move(error), *document, queue());
    }
    return 0;
}

extern "C" WEBCORE_EXPORT int32_t ranvier_test_okp_status() { return job().status; }
extern "C" WEBCORE_EXPORT int32_t ranvier_test_okp_boolean() { return job().boolean; }
extern "C" WEBCORE_EXPORT int32_t ranvier_test_okp_bytes(uint8_t* buffer, int32_t capacity)
{
    if (job().status != 1 || capacity < 0 || static_cast<size_t>(capacity) < job().bytes.size())
        return -1;
    if (!job().bytes.isEmpty())
        memcpy(buffer, job().bytes.span().data(), job().bytes.size());
    return static_cast<int32_t>(job().bytes.size());
}
extern "C" WEBCORE_EXPORT const char* ranvier_test_okp_error()
{
    if (!job().error)
        return "";
    switch (*job().error) {
    case ExceptionCode::InvalidAccessError: return "InvalidAccessError";
    case ExceptionCode::OperationError: return "OperationError";
    case ExceptionCode::DataError: return "DataError";
    case ExceptionCode::SyntaxError: return "SyntaxError";
    default: return "UnexpectedError";
    }
}
extern "C" WEBCORE_EXPORT void ranvier_test_okp_clear()
{
    ++job().generation;
    secureZeroSpan(job().bytes.mutableSpan());
    job().bytes.clear();
    job().status = 0;
    job().error = std::nullopt;
}

#undef EXPECT_PORT
