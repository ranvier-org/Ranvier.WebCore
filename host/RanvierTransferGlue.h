#pragma once

#include "RanvierWebCoreAbi.h"
#include <WebCore/PlatformExportMacros.h>
#include <memory>
#include <wtf/Forward.h>
#include <wtf/Vector.h>
#include <wtf/text/WTFString.h>

namespace WebCore {
class DataTransfer;
class Document;
class Element;
class File;
class IntPoint;
class Pasteboard;
}

// The contents of a file an app hands to a drop or a paste: a copy of its bytes, with its name and type.
struct RanvierTransferFile {
    String name;
    String type;
    Vector<uint8_t> bytes;
};

// Contract:
// - ranvierTransferPasteboard returns a read-only pasteboard of the strings, in order, and of the files as in-memory
//   file contents (FileContentState::InMemoryImage); writes to it are ignored. A DataTransfer over it lists the
//   strings' types, reads their values, and makes a new File for each file, with its name, type and bytes.
// - ranvierDropTransfer returns the data transfer of a drag event from outside over such a pasteboard, with the
//   RV_DROP_* operations allowed: read-only for drop, protected for dragenter, dragover and dragleave.
// - ranvierTransferFiles returns the Files of the data transfer's item list, in order.
// - ranvierTransferDragImage writes the element setDragImage set and its offset, and returns false when none is set.
// - ranvier_replace_range replaces the range with the text as an insertReplacementText edit: beforeinput, cancelable,
//   with the range as its target range, then the edit and input. Returns 1 when the edit applied, else 0.
WEBCORE_EXPORT std::unique_ptr<WebCore::Pasteboard> ranvierTransferPasteboard(const Vector<std::pair<String, String>>& strings,
    const Vector<RanvierTransferFile>& files);
WEBCORE_EXPORT Ref<WebCore::DataTransfer> ranvierDropTransfer(WebCore::Document&, const Vector<std::pair<String, String>>& strings,
    const Vector<RanvierTransferFile>& files, int32_t allowed, bool drop);
WEBCORE_EXPORT Vector<Ref<WebCore::File>> ranvierTransferFiles(WebCore::DataTransfer&, WebCore::Document&);
WEBCORE_EXPORT bool ranvierTransferDragImage(WebCore::DataTransfer&, RefPtr<WebCore::Element>&, WebCore::IntPoint&);
extern "C" {
WEBCORE_EXPORT int32_t ranvier_replace_range(RvAbstractRange* range, const uint8_t* text, int32_t length);
}
