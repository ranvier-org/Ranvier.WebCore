#pragma once

#include "RanvierCryptoAsymmetricContract.h"

typedef struct RanvierCryptoImportParams {
    uint32_t size;
    RanvierCryptoBytes name;
    const RanvierCryptoHmacImportParams* hmac;
    const RanvierCryptoAsymmetricKeyParams* asymmetric;
} RanvierCryptoImportParams;

typedef struct RanvierCryptoWrappingParams {
    uint32_t size;
    RanvierCryptoBytes name;
    const RanvierCryptoAesCipherParams* aes;
    const RanvierCryptoAsymmetricOaepParams* oaep;
} RanvierCryptoWrappingParams;
