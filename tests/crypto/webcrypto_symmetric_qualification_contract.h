#pragma once

#include "RanvierCryptoContract.h"

struct SymmetricQualificationRequest {
    int32_t size;
    int32_t algorithm;
    int32_t operation;
    int32_t parameter;
    int32_t hash;
    int32_t lengthBits;
    uint32_t iterations;
    int32_t extractable;
    int32_t saltPresent;
    RanvierCryptoBytes key;
    RanvierCryptoBytes iv;
    RanvierCryptoBytes additionalData;
    RanvierCryptoBytes input;
    RanvierCryptoBytes salt;
    RanvierCryptoBytes info;
};

struct SymmetricQualificationResult {
    int32_t size;
    int32_t exceptionCode;
    const char* exceptionName;
    int32_t ownerThread;
    int32_t callbackDuringStart;
    int32_t backendCallbackInline;
    int32_t borrowedKeyRetains;
    int32_t keyBits;
    int32_t extractable;
    uint32_t usages;
    int32_t terminalCount;
    RanvierCryptoBytes output;
};

using SymmetricQualificationCallback = void (*)(void*, const SymmetricQualificationResult*);

enum class SymmetricAlgorithm : int32_t { CBC = 1, CTR, GCM, KW, HKDF, PBKDF2 };
enum class SymmetricOperation : int32_t {
    Export = 1, Encrypt, Decrypt, Wrap, Unwrap, DeriveBits, DeriveImportExport,
    GenerateExport, ImportInfo, CbcRawEncrypt, CbcRawDecrypt
};
