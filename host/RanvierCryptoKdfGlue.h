#pragma once

#include "RanvierCryptoKdfContract.h"
#include "RanvierWebCoreAbi.h"
#include <WebCore/PlatformExportMacros.h>

extern "C" {
WEBCORE_EXPORT int32_t ranvier_crypto_kdf_supported(RvNode*, RanvierCryptoBytes name, int32_t*);
WEBCORE_EXPORT int32_t ranvier_crypto_kdf_derive_bits(RvNode*, const RanvierCryptoKdfParams*, RanvierCryptoKeyHandle, RanvierCryptoOptionalLength, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_kdf_derive_key(RvNode*, const RanvierCryptoKdfParams*, RanvierCryptoKeyHandle, const RanvierCryptoDerivedKeyParams*, int32_t extractable, RanvierCryptoStrings usages, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_kdf_key_info(RanvierCryptoKeyHandle, RanvierCryptoKdfKeyInfo*);
}
