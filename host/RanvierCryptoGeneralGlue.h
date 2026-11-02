#pragma once

#include "RanvierCryptoGeneralContract.h"
#include "RanvierWebCoreAbi.h"
#include <WebCore/PlatformExportMacros.h>

extern "C" {
WEBCORE_EXPORT int32_t ranvier_crypto_key_import(RvNode*, RanvierCryptoBytes format, const RanvierCryptoAsymmetricKeyData*, const RanvierCryptoImportParams*, int32_t extractable, RanvierCryptoStrings usages, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_key_wrap(RvNode*, RanvierCryptoBytes format, RanvierCryptoKeyHandle key, RanvierCryptoKeyHandle wrappingKey, const RanvierCryptoWrappingParams*, RanvierCryptoOperationHandle*);
WEBCORE_EXPORT int32_t ranvier_crypto_key_unwrap(RvNode*, RanvierCryptoBytes format, RanvierCryptoBytes wrapped, RanvierCryptoKeyHandle unwrappingKey, const RanvierCryptoWrappingParams*, const RanvierCryptoImportParams*, int32_t extractable, RanvierCryptoStrings usages, RanvierCryptoOperationHandle*);
}
