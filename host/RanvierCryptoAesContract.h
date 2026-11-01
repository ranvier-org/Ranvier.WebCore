#pragma once

#include "RanvierCryptoContract.h"

typedef struct RanvierCryptoOptionalString {
    int32_t present;
    RanvierCryptoBytes value;
} RanvierCryptoOptionalString;

typedef struct RanvierCryptoOptionalStrings {
    int32_t present;
    RanvierCryptoStrings value;
} RanvierCryptoOptionalStrings;

typedef struct RanvierCryptoAesKeyGenParams {
    uint32_t size;
    RanvierCryptoBytes name;
    int32_t length_present;
    uint32_t length_bits;
} RanvierCryptoAesKeyGenParams;

typedef struct RanvierCryptoAesCbcParams {
    uint32_t size;
    int32_t iv_present;
    RanvierCryptoBytes iv;
} RanvierCryptoAesCbcParams;

typedef struct RanvierCryptoAesCtrParams {
    uint32_t size;
    int32_t counter_present;
    RanvierCryptoBytes counter;
    int32_t length_present;
    uint32_t length_bits;
} RanvierCryptoAesCtrParams;

typedef struct RanvierCryptoAesGcmParams {
    uint32_t size;
    int32_t iv_present;
    RanvierCryptoBytes iv;
    int32_t additional_data_present;
    RanvierCryptoBytes additional_data;
    int32_t tag_length_present;
    uint32_t tag_length_bits;
} RanvierCryptoAesGcmParams;

typedef struct RanvierCryptoAesCipherParams {
    uint32_t size;
    RanvierCryptoBytes name;
    const RanvierCryptoAesCbcParams* cbc;
    const RanvierCryptoAesCtrParams* ctr;
    const RanvierCryptoAesGcmParams* gcm;
} RanvierCryptoAesCipherParams;

typedef struct RanvierCryptoOctetJwk {
    uint32_t size;
    RanvierCryptoOptionalString kty;
    RanvierCryptoOptionalString k;
    RanvierCryptoOptionalString alg;
    RanvierCryptoOptionalString use;
    RanvierCryptoOptionalStrings key_ops;
    int32_t ext_present;
    int32_t ext;
} RanvierCryptoOctetJwk;

typedef struct RanvierCryptoSecretKeyData {
    uint32_t size;
    int32_t raw_present;
    RanvierCryptoBytes raw;
    const RanvierCryptoOctetJwk* jwk;
} RanvierCryptoSecretKeyData;

typedef struct RanvierCryptoHmacImportParams {
    uint32_t size;
    int32_t hash_present;
    RanvierCryptoBytes hash;
    int32_t length_present;
    uint32_t length_bits;
} RanvierCryptoHmacImportParams;

typedef struct RanvierCryptoSecretImportParams {
    uint32_t size;
    RanvierCryptoBytes name;
    const RanvierCryptoHmacImportParams* hmac;
} RanvierCryptoSecretImportParams;

typedef struct RanvierCryptoAesKeyInfo {
    uint32_t size;
    int32_t extractable;
    uint64_t length_bits;
    int32_t can_encrypt;
    int32_t can_decrypt;
    int32_t can_wrap;
    int32_t can_unwrap;
} RanvierCryptoAesKeyInfo;
