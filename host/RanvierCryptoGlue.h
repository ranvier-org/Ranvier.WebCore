#pragma once

#include "RanvierCryptoContract.h"
#include "RanvierWebCoreAbi.h"
#include <WebCore/PlatformExportMacros.h>

// Calls require the main thread. Inputs are copied before admission returns.
// Tokens own references until release; keys can outlive their admitting document.
extern "C" {
WEBCORE_EXPORT int32_t ranvier_crypto_hmac_supported(RvNode* document, int32_t* supported);
WEBCORE_EXPORT int32_t ranvier_crypto_hmac_generate(RvNode*, const RanvierCryptoHmacParams*, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_hmac_import_raw(RvNode*, const RanvierCryptoHmacParams*, RanvierCryptoBytes, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_hmac_export_raw(RvNode*, RanvierCryptoKeyHandle, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_hmac_sign(RvNode*, RanvierCryptoKeyHandle, RanvierCryptoBytes, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_hmac_verify(RvNode*, RanvierCryptoKeyHandle, RanvierCryptoBytes signature, RanvierCryptoBytes data, RanvierCryptoOperationHandle*);

// Ready becomes true after owner-context delivery, or on context teardown (AbortError).
// Error names are UTF-8 without a terminator; success has length zero. Pending reads return RV_ERR_UNSUPPORTED.
WEBCORE_EXPORT int32_t ranvier_crypto_operation_ready(RanvierCryptoOperationHandle, int32_t*);
WEBCORE_EXPORT int32_t ranvier_crypto_operation_error(RanvierCryptoOperationHandle, char*, int32_t capacity, int32_t* length);
WEBCORE_EXPORT int32_t ranvier_crypto_operation_take_key(RanvierCryptoOperationHandle, RanvierCryptoKeyHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_operation_bytes(RanvierCryptoOperationHandle, uint8_t*, int32_t capacity, int32_t* length);
WEBCORE_EXPORT int32_t ranvier_crypto_operation_boolean(RanvierCryptoOperationHandle, int32_t*);
WEBCORE_EXPORT int32_t ranvier_crypto_operation_release(RanvierCryptoOperationHandle);

// Taking a key transfers the result once. Byte/boolean snapshots remain readable until operation release.
WEBCORE_EXPORT int32_t ranvier_crypto_key_retain(RanvierCryptoKeyHandle);
WEBCORE_EXPORT int32_t ranvier_crypto_key_release(RanvierCryptoKeyHandle);
WEBCORE_EXPORT int32_t ranvier_crypto_hmac_key_info(RanvierCryptoKeyHandle, RanvierCryptoHmacKeyInfo*);
WEBCORE_EXPORT int32_t ranvier_crypto_hmac_key_hash(RanvierCryptoKeyHandle, char*, int32_t capacity, int32_t* length);
}
