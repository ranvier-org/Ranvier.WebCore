#pragma once

#include <cstdint>

struct AsymmetricBytes { const uint8_t* data; int32_t length; };
struct AsymmetricRequest {
    int32_t size;
    int32_t algorithm;
    int32_t operation;
    int32_t format;
    int32_t hash;
    int32_t curve;
    int64_t parameter;
    int32_t extractable;
    uint32_t usages;
    void* key;
    void* peer;
    AsymmetricBytes input;
    AsymmetricBytes signature;
    AsymmetricBytes label;
    AsymmetricBytes exponent;
    AsymmetricBytes jwk[14];
    int32_t jwkExt;
};
struct AsymmetricResult {
    int32_t size;
    int32_t exceptionCode;
    const char* exceptionName;
    int32_t ownerThread;
    int32_t terminalCount;
    int32_t callbackDuringStart;
    int32_t borrowedRetains;
    int32_t verified;
    int32_t keyType;
    int32_t extractable;
    uint32_t usages;
    int32_t modulusBits;
    int32_t hashBits;
    int32_t algorithm;
    int32_t curve;
    void* firstKey;
    void* secondKey;
    AsymmetricBytes output;
    AsymmetricBytes exponent;
    AsymmetricBytes jwk[14];
    int32_t jwkExt;
};
using AsymmetricCallback = void (*)(void*, const AsymmetricResult*);
