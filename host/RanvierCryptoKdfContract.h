#pragma once

#include "RanvierCryptoAesContract.h"

typedef struct RanvierCryptoHkdfParams {
    uint32_t size;
    int32_t hash_present;
    RanvierCryptoBytes hash;
    int32_t salt_present;
    RanvierCryptoBytes salt;
    int32_t info_present;
    RanvierCryptoBytes info;
} RanvierCryptoHkdfParams;

typedef struct RanvierCryptoPbkdf2Params {
    uint32_t size;
    int32_t salt_present;
    RanvierCryptoBytes salt;
    int32_t iterations_present;
    uint64_t iterations;
    int32_t hash_present;
    RanvierCryptoBytes hash;
} RanvierCryptoPbkdf2Params;

typedef struct RanvierCryptoKdfParams {
    uint32_t size;
    RanvierCryptoBytes name;
    const RanvierCryptoHkdfParams* hkdf;
    const RanvierCryptoPbkdf2Params* pbkdf2;
} RanvierCryptoKdfParams;

typedef struct RanvierCryptoOptionalLength {
    int32_t present;
    uint64_t bits;
} RanvierCryptoOptionalLength;

typedef struct RanvierCryptoDerivedAesParams {
    uint32_t size;
    int32_t length_present;
    uint32_t length_bits;
} RanvierCryptoDerivedAesParams;

typedef struct RanvierCryptoDerivedKeyParams {
    uint32_t size;
    RanvierCryptoBytes name;
    const RanvierCryptoDerivedAesParams* aes;
    const RanvierCryptoHmacImportParams* hmac;
} RanvierCryptoDerivedKeyParams;

typedef struct RanvierCryptoKdfKeyInfo {
    uint32_t size;
    int32_t extractable;
    int32_t can_derive_bits;
    int32_t can_derive_key;
} RanvierCryptoKdfKeyInfo;
