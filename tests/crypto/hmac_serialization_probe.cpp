#include "config.h"

#include "CryptoClient.h"
#include "CryptoKey.h"
#include "CryptoKeyHMAC.h"
#include "DOMWrapperWorld.h"
#include "Document.h"
#include "DocumentLoader.h"
#include "DocumentWriter.h"
#include "EmptyClients.h"
#include "FrameLoader.h"
#include "JSCryptoKey.h"
#include "JSDOMGlobalObject.h"
#include "LocalFrame.h"
#include "LocalFrameInlines.h"
#include "LocalFrameView.h"
#include "Page.h"
#include "PageConfiguration.h"
#include "ScriptController.h"
#include "SerializedScriptValue.h"
#include "Settings.h"
#include <JavaScriptCore/JSLock.h>
#include <pal/SessionID.h>
#include <wtf/StdLibExtras.h>
#include <wtf/TZoneMallocInlines.h>

using namespace WebCore;

namespace {

class RoundTripClient final : public CryptoClient {
    WTF_MAKE_TZONE_ALLOCATED_INLINE(RoundTripClient);
public:
    explicit RoundTripClient(uint32_t corruption) : m_corruption(corruption) { }
    ~RoundTripClient() final { secureZeroSpan(m_encoded.mutableSpan()); }

    // Test-only identity wrapping lets the real serializer/deserializer exercise the key schema.
    std::optional<Vector<uint8_t>> serializeAndWrapCryptoKey(CryptoKeyData&& data) const final
    {
        auto key = CryptoKey::create(WTF::move(data));
        if (!key)
            return std::nullopt;
        m_encoded = SerializedScriptValue::serializeCryptoKey(*key);
        return m_encoded;
    }

    std::optional<Vector<uint8_t>> unwrapCryptoKey(const Vector<uint8_t>& bytes) const final
    {
        auto result = bytes;
        if (m_corruption && result.size() >= 8) {
            auto tail = result.mutableSpan().last(8);
            switch (m_corruption) {
            case 1:
                std::ranges::fill(tail, 0);
                break;
            case 2:
                std::ranges::fill(tail, 0xff);
                break;
            case 3:
                result.removeLast();
                break;
            case 4:
                std::ranges::fill(tail, 0);
                tail[0] = 152;
                break;
            case 5:
                if (result.size() < 10)
                    return std::nullopt;
                result[result.size() - 10] |= 1;
                break;
            case 6:
                if (result.size() < 8)
                    return std::nullopt;
                result[4] = 3;
                break;
            default:
                return std::nullopt;
            }
        }
        return result;
    }

    const Vector<uint8_t>& encoded() const { return m_encoded; }

private:
    uint32_t m_corruption;
    mutable Vector<uint8_t> m_encoded;
};

uint64_t logicalLength(CryptoKey& key)
{
    auto algorithm = key.algorithm();
    auto* hmac = std::get_if<CryptoHmacKeyAlgorithm>(&algorithm);
    return hmac ? hmac->length : 0;
}

RefPtr<CryptoKeyHMAC> makeKey(uint32_t bits)
{
    Vector<uint8_t> material(20);
    material.fill(0x0b);
    return CryptoKeyHMAC::importRaw(bits, CryptoAlgorithmIdentifier::SHA_256, WTF::move(material),
        true, CryptoKeyUsageSign | CryptoKeyUsageVerify);
}

}

// This unit is linked only into the private proof runtime, never the packaged host.
extern "C" WEBCORE_EXPORT int32_t ranvier_test_hmac_serialization(uint32_t bits, uint32_t corruption)
{
    auto key = makeKey(bits);
    if (!key)
        return 1;
    auto expectedBits = bits ? bits : 160;
    auto dataCopy = CryptoKey::create(static_cast<CryptoKey&>(*key).data());
    if (!dataCopy || logicalLength(*key) != expectedBits || logicalLength(*dataCopy) != expectedBits
        || !equalSpans(key->key().span(), downcast<CryptoKeyHMAC>(*dataCopy).key().span()))
        return 2;
    auto direct = SerializedScriptValue::serializeCryptoKey(*key);
    if (direct.size() < 8 || direct[4] != (expectedBits % 8 ? 2 : 1) || direct[5] || direct[6] || direct[7])
        return 3;

    auto client = makeUniqueRef<RoundTripClient>(corruption);
    auto& clientReference = client.get();
    auto configuration = pageConfigurationWithEmptyClients(std::nullopt, PAL::SessionID::defaultSessionID());
    configuration.cryptoClient = WTF::move(client);
    Ref page = Page::create(WTF::move(configuration));
    page->settings().setScriptEnabled(false);
    RefPtr frame = page->localMainFrame();
    if (!frame)
        return 4;
    frame->setView(LocalFrameView::create(*frame, { 320, 200 }));
    frame->init();
    auto& writer = frame->loader().activeDocumentLoader()->writer();
    writer.setMIMEType("text/html"_s);
    writer.begin(URL { "https://crypto.test/"_s });
    writer.insertDataSynchronously("<p>native serialization fixture</p>"_s);
    writer.end();
    auto* global = frame->script().globalObject(mainThreadNormalWorldSingleton());
    if (!global || !frame->document()->isSecureContext())
        return 5;
    JSC::JSLockHolder lock(global->vm());
    Ref<CryptoKey> boxedKey = key.releaseNonNull();
    auto serialized = SerializedScriptValue::create(*global, toJS(global, global, WTF::move(boxedKey)),
        SerializationForStorage::No, SerializationErrorMode::NonThrowing);
    if (!serialized || !equalSpans(clientReference.encoded().span(), direct.span()))
        return 6;
    bool failed = false;
    auto restored = serialized->deserialize(*global, global, SerializationErrorMode::NonThrowing, &failed);
    if (corruption)
        return failed ? 0 : 7;
    RefPtr restoredKey = JSCryptoKey::toWrapped(global->vm(), restored);
    if (failed || !restoredKey || logicalLength(*restoredKey) != expectedBits)
        return 8;
    if (!equalSpans(downcast<CryptoKeyHMAC>(*restoredKey).key().span(), downcast<CryptoKeyHMAC>(*dataCopy).key().span()))
        return 9;
    return 0;
}

extern "C" WEBCORE_EXPORT int32_t ranvier_test_hmac_wire(uint32_t bits, uint8_t* buffer, int32_t capacity, int32_t* length)
{
    if (!length || capacity < 0 || (capacity && !buffer))
        return -1;
    auto key = makeKey(bits);
    if (!key)
        return -9;
    auto encoded = SerializedScriptValue::serializeCryptoKey(*key);
    *length = encoded.size();
    if (encoded.size() > static_cast<size_t>(capacity))
        return -6;
    memcpy(buffer, encoded.span().data(), encoded.size());
    secureZeroSpan(encoded.mutableSpan());
    return 0;
}
