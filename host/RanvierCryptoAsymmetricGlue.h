#pragma once

#include "RanvierCryptoAsymmetricContract.h"
#include "RanvierWebCoreAbi.h"
#include <WebCore/PlatformExportMacros.h>

extern "C" {
WEBCORE_EXPORT int32_t ranvier_crypto_asymmetric_supported(RvNode*, RanvierCryptoBytes name, int32_t*);
WEBCORE_EXPORT int32_t ranvier_crypto_asymmetric_generate(RvNode*, const RanvierCryptoAsymmetricKeyParams*, int32_t extractable, RanvierCryptoStrings usages, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_asymmetric_import(RvNode*, RanvierCryptoBytes format, const RanvierCryptoAsymmetricKeyData*, const RanvierCryptoAsymmetricKeyParams*, int32_t extractable, RanvierCryptoStrings usages, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_asymmetric_sign(RvNode*, const RanvierCryptoAsymmetricSignParams*, RanvierCryptoKeyHandle, RanvierCryptoBytes data, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_asymmetric_verify(RvNode*, const RanvierCryptoAsymmetricSignParams*, RanvierCryptoKeyHandle, RanvierCryptoBytes signature, RanvierCryptoBytes data, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_asymmetric_encrypt(RvNode*, const RanvierCryptoAsymmetricOaepParams*, RanvierCryptoKeyHandle, RanvierCryptoBytes data, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_asymmetric_decrypt(RvNode*, const RanvierCryptoAsymmetricOaepParams*, RanvierCryptoKeyHandle, RanvierCryptoBytes data, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_asymmetric_derive_bits(RvNode*, const RanvierCryptoAsymmetricDeriveParams*, RanvierCryptoKeyHandle, RanvierCryptoOptionalLength, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_asymmetric_derive_key(RvNode*, const RanvierCryptoAsymmetricDeriveParams*, RanvierCryptoKeyHandle, const RanvierCryptoDerivedKeyParams*, int32_t extractable, RanvierCryptoStrings usages, RanvierCryptoOperationHandle*);

WEBCORE_EXPORT int32_t ranvier_crypto_operation_take_key_pair(RanvierCryptoOperationHandle, RanvierCryptoKeyPairResult*);
WEBCORE_EXPORT int32_t ranvier_crypto_operation_jwk(RanvierCryptoOperationHandle, RanvierCryptoJsonWebKey*);
}
