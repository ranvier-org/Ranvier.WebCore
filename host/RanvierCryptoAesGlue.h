#pragma once

#include "RanvierCryptoAesContract.h"
#include "RanvierWebCoreAbi.h"
#include <WebCore/PlatformExportMacros.h>

// Inputs are copied during admission; terminal delivery and handle access require the owner thread.
extern "C" {
WEBCORE_EXPORT int32_t ranvier_crypto_aes_supported(RvNode*, RanvierCryptoBytes name, int32_t*);
WEBCORE_EXPORT int32_t ranvier_crypto_aes_generate(RvNode*, const RanvierCryptoAesKeyGenParams*, int32_t extractable, RanvierCryptoStrings usages, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_secret_import(RvNode*, RanvierCryptoBytes format, const RanvierCryptoSecretKeyData*, const RanvierCryptoSecretImportParams*, int32_t extractable, RanvierCryptoStrings usages, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_key_export(RvNode*, RanvierCryptoBytes format, RanvierCryptoKeyHandle, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_aes_encrypt(RvNode*, const RanvierCryptoAesCipherParams*, RanvierCryptoKeyHandle, RanvierCryptoBytes, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_aes_decrypt(RvNode*, const RanvierCryptoAesCipherParams*, RanvierCryptoKeyHandle, RanvierCryptoBytes, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_aes_wrap(RvNode*, RanvierCryptoBytes format, RanvierCryptoKeyHandle key, RanvierCryptoKeyHandle wrapping_key, const RanvierCryptoAesCipherParams*, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_aes_unwrap(RvNode*, RanvierCryptoBytes format, RanvierCryptoBytes wrapped, RanvierCryptoKeyHandle unwrapping_key, const RanvierCryptoAesCipherParams*, const RanvierCryptoSecretImportParams*, int32_t extractable, RanvierCryptoStrings usages, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_aes_key_info(RanvierCryptoKeyHandle, RanvierCryptoAesKeyInfo*);
WEBCORE_EXPORT int32_t ranvier_crypto_key_algorithm_name(RanvierCryptoKeyHandle, char*, int32_t capacity, int32_t* length);
WEBCORE_EXPORT int32_t ranvier_crypto_key_type(RanvierCryptoKeyHandle, char*, int32_t capacity, int32_t* length);

// Snapshot spans belong to the completed operation and remain valid until operation release.
WEBCORE_EXPORT int32_t ranvier_crypto_operation_octet_jwk(RanvierCryptoOperationHandle, RanvierCryptoOctetJwk*);
}
