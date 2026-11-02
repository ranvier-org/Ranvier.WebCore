#pragma once

#include "RanvierCryptoAesContract.h"
#include "RanvierCryptoKdfContract.h"

typedef struct RanvierCryptoRsaOtherPrime {
    RanvierCryptoOptionalString r;
    RanvierCryptoOptionalString d;
    RanvierCryptoOptionalString t;
} RanvierCryptoRsaOtherPrime;

typedef struct RanvierCryptoOptionalOtherPrimes {
    int32_t present;
    const RanvierCryptoRsaOtherPrime* items;
    int32_t count;
} RanvierCryptoOptionalOtherPrimes;

typedef struct RanvierCryptoJsonWebKey {
    uint32_t size;
    RanvierCryptoOptionalString kty;
    RanvierCryptoOptionalString k;
    RanvierCryptoOptionalString alg;
    RanvierCryptoOptionalString use;
    RanvierCryptoOptionalString crv;
    RanvierCryptoOptionalString x;
    RanvierCryptoOptionalString y;
    RanvierCryptoOptionalString d;
    RanvierCryptoOptionalString n;
    RanvierCryptoOptionalString e;
    RanvierCryptoOptionalString p;
    RanvierCryptoOptionalString q;
    RanvierCryptoOptionalString dp;
    RanvierCryptoOptionalString dq;
    RanvierCryptoOptionalString qi;
    RanvierCryptoOptionalStrings key_ops;
    int32_t ext_present;
    int32_t ext;
    RanvierCryptoOptionalOtherPrimes oth;
} RanvierCryptoJsonWebKey;

typedef struct RanvierCryptoKeyPairResult {
    uint32_t size;
    RanvierCryptoKeyHandle public_key;
    RanvierCryptoKeyHandle private_key;
} RanvierCryptoKeyPairResult;

typedef struct RanvierCryptoAsymmetricKeyParams {
    uint32_t size;
    RanvierCryptoBytes name;
    RanvierCryptoOptionalString hash;
    RanvierCryptoOptionalString named_curve;
    int32_t modulus_length_present;
    uint64_t modulus_length_bits;
    int32_t public_exponent_present;
    RanvierCryptoBytes public_exponent;
} RanvierCryptoAsymmetricKeyParams;

typedef struct RanvierCryptoAsymmetricSignParams {
    uint32_t size;
    RanvierCryptoBytes name;
    RanvierCryptoOptionalString hash;
    int32_t salt_length_present;
    uint64_t salt_length_bytes;
} RanvierCryptoAsymmetricSignParams;

typedef struct RanvierCryptoAsymmetricOaepParams {
    uint32_t size;
    RanvierCryptoBytes name;
    int32_t label_present;
    RanvierCryptoBytes label;
} RanvierCryptoAsymmetricOaepParams;

typedef struct RanvierCryptoAsymmetricDeriveParams {
    uint32_t size;
    RanvierCryptoBytes name;
    int32_t public_key_present;
    RanvierCryptoKeyHandle public_key;
} RanvierCryptoAsymmetricDeriveParams;

typedef struct RanvierCryptoAsymmetricKeyData {
    uint32_t size;
    int32_t raw_present;
    RanvierCryptoBytes raw;
    const RanvierCryptoJsonWebKey* jwk;
} RanvierCryptoAsymmetricKeyData;

typedef struct RanvierCryptoAsymmetricKeyInfo {
    uint32_t size;
    int32_t modulus_length_present;
    uint64_t modulus_length_bits;
    int32_t hash_present;
    int32_t named_curve_present;
} RanvierCryptoAsymmetricKeyInfo;
