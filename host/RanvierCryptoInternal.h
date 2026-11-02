#pragma once

#include "RanvierCryptoAsymmetricContract.h"
#include "RanvierWebCoreAbi.h"
#include "CryptoAlgorithm.h"
#include "ExceptionOr.h"
#include "JsonWebKey.h"
#include <wtf/RefPtr.h>
#include <wtf/Vector.h>
#include <wtf/WorkQueue.h>
#include <memory>
#include <optional>

namespace WebCore {
class Document;
}

namespace Ranvier::Crypto {

int32_t documentOf(RvNode*, WebCore::Document*&);
int32_t lookupKey(RanvierCryptoKeyHandle, RefPtr<WebCore::CryptoKey>&);
uint64_t admit(WebCore::Document&, RanvierCryptoOperationHandle*);
WebCore::Document* pendingDocument(uint64_t);
WTF::WorkQueue& queue();

void deliverError(uint64_t, WebCore::ExceptionCode);
void deliverBytes(uint64_t, const Vector<uint8_t>&);
void deliverBoolean(uint64_t, bool);
void deliverKey(uint64_t, WebCore::CryptoKey&);
void deliverKeyPair(uint64_t, WebCore::CryptoKey& publicKey, WebCore::CryptoKey& privateKey);
void deliverJwk(uint64_t, WebCore::JsonWebKey&&);

bool validJwk(const RanvierCryptoJsonWebKey*);
std::optional<WebCore::ExceptionCode> copyJwk(const RanvierCryptoJsonWebKey&, WebCore::JsonWebKey&);
std::optional<WebCore::ExceptionCode> normalizeUsages(RanvierCryptoStrings, WebCore::CryptoKeyUsageBitmap&);

class DerivedKeyTarget;
bool validDerivedTarget(const RanvierCryptoDerivedKeyParams*);
std::optional<WebCore::ExceptionCode> normalizeDerivedTarget(const RanvierCryptoDerivedKeyParams&, bool extractable,
    RanvierCryptoStrings, std::shared_ptr<DerivedKeyTarget>&);
WebCore::ExceptionOr<std::optional<size_t>> derivedTargetLength(const DerivedKeyTarget&);
void importDerivedKey(uint64_t, const std::shared_ptr<DerivedKeyTarget>&, Vector<uint8_t>&&);

bool validAsymmetricKeyParams(const RanvierCryptoAsymmetricKeyParams*);
bool validAsymmetricOaepParams(const RanvierCryptoAsymmetricOaepParams*);
std::optional<WebCore::ExceptionCode> normalizeAsymmetricImport(const RanvierCryptoAsymmetricKeyParams&,
    std::unique_ptr<WebCore::CryptoAlgorithmParameters>&);
std::optional<WebCore::ExceptionCode> normalizeAsymmetricOaep(const RanvierCryptoAsymmetricOaepParams&,
    std::unique_ptr<WebCore::CryptoAlgorithmParameters>&);

}
