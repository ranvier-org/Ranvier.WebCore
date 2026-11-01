#include "config.h"
#include "RanvierTransferGlue.h"
#include "AbstractRange.h"
#include "BoundaryPointInlines.h"
#include "DataTransfer.h"
#include "DataTransferItem.h"
#include "DataTransferItemList.h"
#include "DragActions.h"
#include "Document.h"
#include "Editor.h"
#include "Element.h"
#include "File.h"
#include "FrameSelection.h"
#include "FrameDestructionObserverInlines.h"
#include "IntPoint.h"
#include "LocalFrame.h"
#include "LocalFrameInlines.h"
#include "Pasteboard.h"
#include "ReplaceRangeWithTextCommand.h"
#include "SharedBuffer.h"
#include "SimpleRange.h"
#include "VisibleSelection.h"

using namespace WebCore;

namespace {

// The strings and in-memory files of a drop or a paste, read as StaticPasteboard reads what a page wrote.
class TransferPasteboard final : public Pasteboard {
public:
    TransferPasteboard(const Vector<std::pair<String, String>>& strings, const Vector<RanvierTransferFile>& files)
        : Pasteboard({ })
        , m_strings(strings)
        , m_files(files)
    {
    }

    bool hasData() final { return !m_strings.isEmpty() || !m_files.isEmpty(); }
    Vector<String> typesSafeForBindings(const String&) final { return types(); }
    Vector<String> typesForLegacyUnsafeBindings() final { return types(); }
    String readOrigin() final { return { }; }
    String readString(const String& type) final
    {
        for (auto& [itemType, value] : m_strings) {
            if (itemType == type)
                return value;
        }
        return { };
    }
    String readStringInCustomData(const String& type) final { return readString(type); }

    void writeString(const String&, const String&) final { }
    void clear() final { }
    void clear(const String&) final { }

    void read(PasteboardPlainText& text, PlainTextURLReadingPolicy, std::optional<size_t>) final { text.text = readString("text/plain"_s); }
    // The host inserts a paste or drop itself; DataTransfer reads strings through readString.
    void read(PasteboardWebContentReader&, WebContentReadingPolicy, std::optional<size_t>) final { }
    void read(PasteboardFileReader& reader, std::optional<size_t> index) final
    {
        for (size_t i = 0; i < m_files.size(); ++i) {
            if (index && *index != i)
                continue;
            auto& file = m_files[i];
            if (reader.shouldReadBuffer(file.type))
                reader.readBuffer(file.name, file.type, SharedBuffer::create(file.bytes.span()));
        }
    }

    void write(const PasteboardURL&) final { }
    void write(const PasteboardImage&) final { }
    void write(const PasteboardWebContent&) final { }
    void writeMarkup(const String&) final { }
    void writePlainText(const String&, SmartReplaceOption) final { }
    void writeCustomData(const Vector<PasteboardCustomData>&) final { }

    FileContentState fileContentState() final { return m_files.isEmpty() ? FileContentState::NoFileOrImageData : FileContentState::InMemoryImage; }
    bool canSmartReplace() final { return false; }

#if ENABLE(DRAG_SUPPORT)
    void setDragImage(DragImage, const IntPoint&) final { }
#endif

private:
    Vector<String> types() const
    {
        Vector<String> result;
        for (auto& [type, value] : m_strings) {
            if (!result.contains(type))
                result.append(type);
        }
        return result;
    }

    Vector<std::pair<String, String>> m_strings;
    Vector<RanvierTransferFile> m_files;
};

}

std::unique_ptr<Pasteboard> ranvierTransferPasteboard(const Vector<std::pair<String, String>>& strings, const Vector<RanvierTransferFile>& files)
{
    return makeUnique<TransferPasteboard>(strings, files);
}

Ref<DataTransfer> ranvierDropTransfer(Document& document, const Vector<std::pair<String, String>>& strings,
    const Vector<RanvierTransferFile>& files, int32_t allowed, bool drop)
{
    OptionSet<DragOperation> operations;
    if (allowed & RV_DROP_COPY)
        operations.add(DragOperation::Copy);
    if (allowed & RV_DROP_MOVE)
        operations.add(DragOperation::Move);
    if (allowed & RV_DROP_LINK)
        operations.add(DragOperation::Link);
    auto pasteboard = ranvierTransferPasteboard(strings, files);
    if (drop)
        return DataTransfer::createForDrop(document, WTF::move(pasteboard), operations, !files.isEmpty());
    return DataTransfer::createForUpdatingDropTarget(document, WTF::move(pasteboard), operations, !files.isEmpty());
}

Vector<Ref<File>> ranvierTransferFiles(DataTransfer& dataTransfer, Document& document)
{
    Vector<Ref<File>> files;
    auto& items = dataTransfer.items(document);
    for (unsigned index = 0; index < items.length(); ++index) {
        if (RefPtr item = items.item(index); item && item->file())
            files.append(*item->file());
    }
    return files;
}

bool ranvierTransferDragImage(DataTransfer& dataTransfer, RefPtr<Element>& element, IntPoint& offset)
{
#if ENABLE(DRAG_SUPPORT)
    element = dataTransfer.dragImageElement();
    offset = dataTransfer.dragLocation();
    return !!element;
#else
    UNUSED_PARAM(dataTransfer);
    UNUSED_PARAM(element);
    UNUSED_PARAM(offset);
    return false;
#endif
}

int32_t ranvier_replace_range(RvAbstractRange* handle, const uint8_t* text, int32_t length)
{
    auto& range = *reinterpret_cast<AbstractRange*>(handle);
    auto simple = makeSimpleRange(range);
    Ref document = simple.start.document();
    RefPtr frame = document->frame();
    if (!frame)
        return 0;
    // The edit's root editable element, which receives beforeinput and input, is the selection's: select the range first,
    // as a spelling correction does.
    frame->selection().setSelection(VisibleSelection { simple });
    Ref command = ReplaceRangeWithTextCommand::create(simple, String::fromUTF8(std::span { text, static_cast<size_t>(length) }));
    command->apply();
    // The editor records the command as its last edit only when the edit applied, after an uncancelled beforeinput.
    return frame->editor().lastEditCommand() == command.ptr() ? 1 : 0;
}
