#pragma once

#include <stdint.h>

typedef struct RanvierCryptoKeyHandle { uint64_t value; } RanvierCryptoKeyHandle;
typedef struct RanvierCryptoOperationHandle { uint64_t value; } RanvierCryptoOperationHandle;

typedef struct RanvierCryptoBytes {
    const uint8_t* data;
    int32_t length;
} RanvierCryptoBytes;

typedef struct RanvierCryptoStrings {
    const RanvierCryptoBytes* items;
    int32_t count;
} RanvierCryptoStrings;

typedef struct RanvierCryptoHmacParams {
    uint32_t size;
    int32_t extractable;
    RanvierCryptoBytes hash;
    int32_t length_present;
    uint32_t length_bits;
    RanvierCryptoStrings usages;
} RanvierCryptoHmacParams;

typedef struct RanvierCryptoHmacKeyInfo {
    uint32_t size;
    int32_t extractable;
    uint64_t length_bits;
    int32_t can_sign;
    int32_t can_verify;
} RanvierCryptoHmacKeyInfo;
