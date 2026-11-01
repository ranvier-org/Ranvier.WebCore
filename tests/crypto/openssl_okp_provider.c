#include <openssl/crypto.h>
#include <openssl/evp.h>
#include <openssl/opensslv.h>
#include <openssl/x509.h>
#include <windows.h>
#include <stdio.h>
#include <string.h>

static int assertions;

static int expect(int condition, const char* label)
{
    ++assertions;
    if (!condition)
        fprintf(stderr, "FAIL %s\n", label);
    return condition;
}

static EVP_PKEY* generate(int type)
{
    EVP_PKEY* key = NULL;
    EVP_PKEY_CTX* context = EVP_PKEY_CTX_new_id(type, NULL);
    if (context && EVP_PKEY_keygen_init(context) == 1 && EVP_PKEY_keygen(context, &key) == 1) {
        EVP_PKEY_CTX_free(context);
        return key;
    }
    EVP_PKEY_CTX_free(context);
    EVP_PKEY_free(key);
    return NULL;
}

static int generated_key_roundtrip(int type)
{
    unsigned char previous[32] = { 0 };
    int iteration;
    for (iteration = 0; iteration < 8; ++iteration) {
        unsigned char secret[32], public_key[32], recovered_public[32];
        unsigned char malformed[33] = { 0 };
        size_t secret_size = sizeof(secret), public_size = sizeof(public_key), recovered_size = sizeof(recovered_public);
        EVP_PKEY* generated = generate(type);
        EVP_PKEY* imported;
        if (!expect(generated != NULL, "actual random key generation"))
            return 0;
        if (!expect(EVP_PKEY_get_raw_private_key(generated, secret, &secret_size) == 1 && secret_size == 32, "generated private material is 32-byte seed/scalar")
            || !expect(EVP_PKEY_get_raw_public_key(generated, public_key, &public_size) == 1 && public_size == 32, "generated public key is 32 bytes")
            || !expect(memcmp(previous, public_key, 32) != 0, "independent generated keys differ")) {
            EVP_PKEY_free(generated);
            return 0;
        }
        memcpy(previous, public_key, 32);
        imported = EVP_PKEY_new_raw_private_key(type, NULL, secret, secret_size);
        if (!expect(imported && EVP_PKEY_get_raw_public_key(imported, recovered_public, &recovered_size) == 1
                && recovered_size == 32 && !memcmp(public_key, recovered_public, 32), "export/import preserves the public key")) {
            EVP_PKEY_free(imported);
            EVP_PKEY_free(generated);
            return 0;
        }
        EVP_PKEY_free(imported);
        imported = EVP_PKEY_new_raw_private_key(type, NULL, malformed, 31);
        if (!expect(!imported, "short raw private key rejected")) {
            EVP_PKEY_free(imported);
            EVP_PKEY_free(generated);
            return 0;
        }
        imported = EVP_PKEY_new_raw_public_key(type, NULL, malformed, 33);
        if (!expect(!imported, "long raw public key rejected")) {
            EVP_PKEY_free(imported);
            EVP_PKEY_free(generated);
            return 0;
        }
        EVP_PKEY_free(generated);
        OPENSSL_cleanse(secret, sizeof(secret));
    }
    return 1;
}

static int ed25519_operations(void)
{
    const unsigned char message[] = { 0, 1, 2, 0, 4, 5 };
    unsigned char signature[64];
    size_t signature_size = sizeof(signature);
    EVP_PKEY* key = generate(EVP_PKEY_ED25519);
    EVP_MD_CTX* sign = EVP_MD_CTX_new();
    EVP_MD_CTX* verify = EVP_MD_CTX_new();
    int ok = expect(key && sign && verify, "Ed25519 test resources");
    if (ok)
        ok = expect(EVP_DigestSignInit(sign, NULL, NULL, NULL, key) == 1
            && EVP_DigestSign(sign, signature, &signature_size, message, sizeof(message)) == 1 && signature_size == 64,
            "generated Ed25519 signs binary message")
            && expect(EVP_DigestVerifyInit(verify, NULL, NULL, NULL, key) == 1
                && EVP_DigestVerify(verify, signature, signature_size, message, sizeof(message)) == 1, "generated Ed25519 signature verifies");
    if (ok) {
        signature[0] ^= 1;
        ok = expect(EVP_DigestVerify(verify, signature, signature_size, message, sizeof(message)) != 1, "wrong Ed25519 signature is false")
            && expect(EVP_DigestVerify(verify, signature, 63, message, sizeof(message)) != 1, "short Ed25519 signature is false");
    }
    if (ok) {
        EVP_MD_CTX_free(sign);
        EVP_MD_CTX_free(verify);
        sign = EVP_MD_CTX_new();
        verify = EVP_MD_CTX_new();
        signature_size = sizeof(signature);
        ok = expect(sign && verify && EVP_DigestSignInit(sign, NULL, NULL, NULL, key) == 1
            && EVP_DigestSign(sign, signature, &signature_size, NULL, 0) == 1 && signature_size == 64, "empty null-span message signs")
            && expect(EVP_DigestVerifyInit(verify, NULL, NULL, NULL, key) == 1
                && EVP_DigestVerify(verify, signature, signature_size, NULL, 0) == 1, "empty null-span signature verifies");
    }
    EVP_MD_CTX_free(sign);
    EVP_MD_CTX_free(verify);
    EVP_PKEY_free(key);
    return ok;
}

static int der_roundtrip(int type)
{
    unsigned char encoded[128], original[32], recovered[32];
    unsigned char malformed[128], canonical[128];
    size_t original_size = sizeof(original), recovered_size = sizeof(recovered);
    unsigned char* output = encoded;
    const unsigned char* input;
    EVP_PKEY* key = generate(type);
    EVP_PKEY* decoded = NULL;
    PKCS8_PRIV_KEY_INFO* info = NULL;
    PKCS8_PRIV_KEY_INFO* parsed_info = NULL;
    const X509_ALGOR* algorithm = NULL;
    const ASN1_OBJECT* object = NULL;
    int parameter_type = 0;
    int length;
    int ok = expect(key != NULL, "DER key generation");
    if (!ok)
        goto done;
    length = i2d_PUBKEY(key, &output);
    input = encoded;
    decoded = length > 0 ? d2i_PUBKEY(NULL, &input, length) : NULL;
    ok = expect(length == 44 && decoded && input == encoded + length && EVP_PKEY_id(decoded) == type,
        "RFC8410 SPKI encode/decode and algorithm identity");
    if (!ok)
        goto done;
    ok = expect(EVP_PKEY_get_raw_public_key(key, original, &original_size) == 1
        && EVP_PKEY_get_raw_public_key(decoded, recovered, &recovered_size) == 1
        && original_size == 32 && recovered_size == 32 && !memcmp(original, recovered, 32), "SPKI preserves public material");
    if (!ok)
        goto done;
    EVP_PKEY_free(decoded);
    decoded = NULL;
    memcpy(malformed, encoded, 9);
    malformed[1] += 2;
    malformed[3] += 2;
    malformed[9] = 5;
    malformed[10] = 0;
    memcpy(malformed + 11, encoded + 9, 35);
    input = malformed;
    decoded = d2i_PUBKEY(NULL, &input, 46);
    output = canonical;
    ok = expect(!decoded || i2d_PUBKEY(decoded, &output) != 46 || memcmp(malformed, canonical, 46),
        "present SPKI parameters cannot survive the canonical import check");
    EVP_PKEY_free(decoded);
    decoded = NULL;
    if (!ok)
        goto done;
    memcpy(malformed, encoded, 44);
    malformed[11] = 1;
    input = malformed;
    decoded = d2i_PUBKEY(NULL, &input, 44);
    output = canonical;
    ok = expect(!decoded || i2d_PUBKEY(decoded, &output) != 44 || memcmp(malformed, canonical, 44),
        "nonzero unused SPKI bits cannot survive the canonical import check");
    EVP_PKEY_free(decoded);
    decoded = NULL;
    if (!ok)
        goto done;
    memcpy(malformed, encoded, 44);
    malformed[44] = 0;
    input = malformed;
    decoded = d2i_PUBKEY(NULL, &input, 45);
    ok = expect(!decoded || input != malformed + 45, "SPKI decoder exposes trailing input for rejection");
    EVP_PKEY_free(decoded);
    decoded = NULL;
    if (!ok)
        goto done;
    memcpy(malformed, encoded, 44);
    malformed[8] = (unsigned char)(type == EVP_PKEY_ED25519 ? 110 : 112);
    input = malformed;
    decoded = d2i_PUBKEY(NULL, &input, 44);
    ok = expect(!decoded || EVP_PKEY_id(decoded) != type, "cross-curve SPKI exposes a different algorithm identity");
    EVP_PKEY_free(decoded);
    decoded = NULL;
    if (!ok)
        goto done;
    info = EVP_PKEY2PKCS8(key);
    output = encoded;
    length = info ? i2d_PKCS8_PRIV_KEY_INFO(info, &output) : 0;
    input = encoded;
    parsed_info = length > 0 ? d2i_PKCS8_PRIV_KEY_INFO(NULL, &input, length) : NULL;
    decoded = parsed_info ? EVP_PKCS82PKEY(parsed_info) : NULL;
    ok = expect(length == 48 && decoded && input == encoded + length && EVP_PKEY_id(decoded) == type,
        "RFC8410 PKCS8 encode/decode and algorithm identity");
    if (!ok)
        goto done;
    original_size = sizeof(original);
    recovered_size = sizeof(recovered);
    ok = expect(EVP_PKEY_get_raw_private_key(key, original, &original_size) == 1
        && EVP_PKEY_get_raw_private_key(decoded, recovered, &recovered_size) == 1
        && original_size == 32 && recovered_size == 32 && !memcmp(original, recovered, 32), "PKCS8 preserves private seed/scalar");
    if (!ok)
        goto done;
    ok = expect(PKCS8_pkey_get0(&object, NULL, NULL, &algorithm, parsed_info) == 1, "PKCS8 algorithm metadata");
    if (!ok)
        goto done;
    X509_ALGOR_get0(&object, &parameter_type, NULL, algorithm);
    ok = expect(OBJ_obj2nid(object) == type && parameter_type == V_ASN1_UNDEF, "RFC8410 parameters are absent");
done:
    EVP_PKEY_free(decoded);
    EVP_PKEY_free(key);
    PKCS8_PRIV_KEY_INFO_free(info);
    PKCS8_PRIV_KEY_INFO_free(parsed_info);
    OPENSSL_cleanse(original, sizeof(original));
    OPENSSL_cleanse(recovered, sizeof(recovered));
    return ok;
}

static int x25519_operations(void)
{
    unsigned char left_secret[32], right_secret[32], zero[32] = { 0 };
    size_t left_size = sizeof(left_secret), right_size = sizeof(right_secret);
    EVP_PKEY* left = generate(EVP_PKEY_X25519);
    EVP_PKEY* right = generate(EVP_PKEY_X25519);
    EVP_PKEY* low_order = EVP_PKEY_new_raw_public_key(EVP_PKEY_X25519, NULL, zero, sizeof(zero));
    EVP_PKEY_CTX* left_context = left ? EVP_PKEY_CTX_new(left, NULL) : NULL;
    EVP_PKEY_CTX* right_context = right ? EVP_PKEY_CTX_new(right, NULL) : NULL;
    int ok = expect(left && right && low_order && left_context && right_context, "X25519 test resources");
    if (ok)
        ok = expect(EVP_PKEY_derive_init(left_context) == 1 && EVP_PKEY_derive_set_peer(left_context, right) == 1
            && EVP_PKEY_derive(left_context, left_secret, &left_size) == 1 && left_size == 32, "generated X25519 agreement")
            && expect(EVP_PKEY_derive_init(right_context) == 1 && EVP_PKEY_derive_set_peer(right_context, left) == 1
                && EVP_PKEY_derive(right_context, right_secret, &right_size) == 1 && right_size == 32
                && !memcmp(left_secret, right_secret, 32), "generated X25519 symmetric agreement");
    if (ok) {
        left_size = sizeof(left_secret);
        ok = expect(EVP_PKEY_derive_set_peer(left_context, low_order) == 1
            && EVP_PKEY_derive(left_context, left_secret, &left_size) != 1, "low-order X25519 peer rejected");
    }
    EVP_PKEY_CTX_free(left_context);
    EVP_PKEY_CTX_free(right_context);
    EVP_PKEY_free(left);
    EVP_PKEY_free(right);
    EVP_PKEY_free(low_order);
    OPENSSL_cleanse(left_secret, sizeof(left_secret));
    OPENSSL_cleanse(right_secret, sizeof(right_secret));
    return ok;
}

int main(void)
{
    HMODULE module = GetModuleHandleA("crypto-57.dll");
    char path[MAX_PATH];
    DWORD length = module ? GetModuleFileNameA(module, path, MAX_PATH) : 0;
    if (!expect(length && length < MAX_PATH, "actual provider DLL path"))
        return 1;
    printf("COMPILE_VERSION=%s\nRUNTIME_VERSION=%s\nRUNTIME_DLL=%s\n", LIBRESSL_VERSION_TEXT, SSLeay_version(SSLEAY_VERSION), path);
    if (!generated_key_roundtrip(EVP_PKEY_ED25519) || !generated_key_roundtrip(EVP_PKEY_X25519)
        || !der_roundtrip(EVP_PKEY_ED25519) || !der_roundtrip(EVP_PKEY_X25519)
        || !ed25519_operations() || !x25519_operations())
        return 1;
    printf("PASS %d provider generation/export/import/invalid-key/signature/agreement assertions\n", assertions);
    return 0;
}
