// Control structure admission bounds traversal independently of control text length.
struct RvImeSegments {
    struct Segment { RefPtr<Node> node; String text; unsigned start; };
    Vector<Segment, 64> items;
    unsigned length { 0 };

    bool read(Element& root)
    {
        for (RefPtr node = root.firstChild(); node; node = node->nextSibling()) {
            if (items.size() == 64 || node->hasChildNodes())
                return false;
            String text;
            if (auto* data = dynamicDowncast<Text>(*node))
                text = data->data(); // Refcounted storage; no scan or copy of the control value.
            else if (node->hasTagName(HTMLNames::brTag))
                text = "\n"_s;
            else
                return false;
            if (text.length() > static_cast<unsigned>(INT32_MAX) - length)
                return false;
            items.append({ node, text, length });
            length += text.length();
        }
        if (length && at(length - 1) == '\n')
            --length; // WebCore's inner editor includes one collapsed terminal newline.
        return true;
    }

    UChar at(unsigned offset) const
    {
        for (const auto& item : items) {
            if (offset >= item.start && offset - item.start < item.text.length())
                return item.text[offset - item.start];
        }
        return 0;
    }

    std::optional<unsigned> offset(Element& root, const BoundaryPoint& point) const
    {
        if (point.container.ptr() == &root) {
            if (point.offset > items.size())
                return std::nullopt;
            return point.offset == items.size() ? length : std::min(length, items[point.offset].start);
        }
        for (const auto& item : items) {
            if (point.container.ptr() == item.node.get() && point.offset <= item.text.length())
                return std::min(length, item.start + point.offset);
        }
        return std::nullopt;
    }

    bool splitsPair(unsigned offset) const
    {
        return offset && offset < length && U16_IS_LEAD(at(offset - 1)) && U16_IS_TRAIL(at(offset));
    }

    String slice(unsigned start, unsigned end) const
    {
        StringBuilder result;
        for (const auto& item : items) {
            auto first = std::max(start, item.start);
            auto last = std::min(end, item.start + item.text.length());
            if (first < last)
                result.append(StringView(item.text).substring(first - item.start, last - first));
        }
        return result.toString();
    }
};

int32_t rv_host_ime_surrounding_window(RvHost* host, int32_t maxUnits, char* buffer, int32_t capacity,
    int32_t* length, int32_t* origin, int32_t* cursor, int32_t* anchor, int32_t* state, uint64_t* token)
{
    if (!host || !length || !origin || !cursor || !anchor || !state || !token || capacity < 0 || maxUnits < 1 || maxUnits > 4096)
        return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread())
        return RV_ERR_WRONG_THREAD;
    if (!liveHosts.contains(host))
        return RV_ERR_DETACHED;
    *length = -1; *origin = *cursor = *anchor = *state = 0; *token = 0;
    host->imeWindow.reset();
    Ref document = host->document();
    RefPtr target = document->focusedElement();
    if (!target)
        return RV_OK;
    if (auto* input = dynamicDowncast<HTMLInputElement>(*target); input && input->isSecureField()) {
        *state = 3;
        return RV_OK;
    }
    *state = 2;
    RefPtr control = dynamicDowncast<HTMLTextFormControlElement>(*target);
    if (!control || !control->isTextField() || host->frame().editor().hasComposition())
        return RV_OK;
    if (control->isDisabledFormControl() || control->hasAttribute(HTMLNames::readonlyAttr)) {
        *state = 0;
        return RV_OK;
    }
    RefPtr root = control->innerTextElement();
    if (!root)
        return RV_OK;
    RvImeSegments segments;
    if (!segments.read(*root))
        return RV_OK;
    auto anchorPoint = makeBoundaryPoint(document->selection().selection().anchor());
    auto cursorPoint = makeBoundaryPoint(document->selection().selection().focus());
    if (!anchorPoint || !cursorPoint)
        return RV_OK;
    auto a = segments.offset(*root, *anchorPoint);
    auto c = segments.offset(*root, *cursorPoint);
    if (!a || !c || segments.splitsPair(*a) || segments.splitsPair(*c))
        return RV_OK;
    auto first = std::min(*a, *c), last = std::max(*a, *c);
    auto limit = static_cast<unsigned>(maxUnits);
    if (last - first > limit)
        return RV_OK;
    unsigned start = first > (limit - (last - first)) / 2 ? first - (limit - (last - first)) / 2 : 0;
    start = std::min(start, segments.length > limit ? segments.length - limit : 0);
    auto end = std::min(segments.length, start + limit);
    if (segments.splitsPair(start)) ++start;
    if (segments.splitsPair(end)) --end;
    if (start > first || end < last)
        return RV_OK;
    auto text = segments.slice(start, end);
    auto bytes = text.utf8(StrictConversion);
    if (bytes.isNull() || text.contains('\0'))
        return RV_OK;
    *length = static_cast<int32_t>(bytes.length());
    *origin = static_cast<int32_t>(start);
    *cursor = static_cast<int32_t>(*c - start);
    *anchor = static_cast<int32_t>(*a - start);
    *state = 1;
    if (!buffer || capacity < *length)
        return RV_ERR_BUFFER_TOO_SMALL;
    std::memcpy(buffer, bytes.data(), bytes.length());
    auto& client = static_cast<RvEditorClient&>(host->page->editorClient());
    auto& chrome = static_cast<RvChromeClient&>(host->page->chrome().client());
    if (!++imeServedSequence) ++imeServedSequence;
    host->imeWindow.emplace(RvHost::ImeWindow { });
    auto& saved = *host->imeWindow;
    saved.token = *token = imeServedSequence;
    saved.document = document.ptr(); saved.target = target.get();
    saved.treeVersion = document->domTreeVersion();
    saved.focusGeneration = chrome.focusGeneration;
    saved.imeGeneration = client.imeGeneration(); saved.historyGeneration = client.historyGeneration();
    saved.editingSequence = host->editingSequence;
    saved.origin = *origin; saved.length = static_cast<int32_t>(text.length());
    saved.cursor = *cursor; saved.anchor = *anchor; saved.text = WTF::move(text);
    return RV_OK;
}

int32_t rv_host_ime_delete_surrounding_window(RvHost* host, uint64_t token, int32_t start, int32_t end)
{
    if (!host) return RV_ERR_NULL_ARGUMENT;
    if (!onOwningThread()) return RV_ERR_WRONG_THREAD;
    if (!liveHosts.contains(host) || !token || !host->imeWindow || host->imeWindow->token != token)
        return RV_ERR_DETACHED;
    auto saved = WTF::move(*host->imeWindow);
    host->imeWindow.reset();
    auto& client = static_cast<RvEditorClient&>(host->page->editorClient());
    auto& chrome = static_cast<RvChromeClient&>(host->page->chrome().client());
    Ref document = host->document();
    if (saved.document.get() != document.ptr() || saved.target.get() != document->focusedElement()
        || saved.treeVersion != document->domTreeVersion() || saved.focusGeneration != chrome.focusGeneration
        || saved.imeGeneration != client.imeGeneration() || saved.historyGeneration != client.historyGeneration()
        || saved.editingSequence != host->editingSequence || host->frame().editor().hasComposition())
        return RV_ERR_DETACHED;
    if (start < 0 || end < start || end > saved.length)
        return RV_ERR_UNSUPPORTED;
    auto splitsPair = [&](int offset) { return offset && offset < saved.length && U16_IS_LEAD(saved.text[offset - 1]) && U16_IS_TRAIL(saved.text[offset]); };
    if (splitsPair(start) || splitsPair(end)) return RV_ERR_UNSUPPORTED;
    if (start == end) return RV_OK;
    // Editing keeps the established beforeinput/reentrancy/undo contract. Only this explicit edit may
    // materialize the full legacy snapshot; repeated bounded context queries never enter this path.
    int32_t length = 0, cursor = 0, anchor = 0, state = 0;
    uint64_t legacyToken = 0;
    auto status = rv_host_ime_surrounding(host, nullptr, 0, &length, &cursor, &anchor, &state, &legacyToken);
    if (status != RV_ERR_BUFFER_TOO_SMALL || state != 1 || length < 0)
        return RV_ERR_UNSUPPORTED;
    Vector<char> bytes(static_cast<size_t>(std::max(1, length)));
    status = rv_host_ime_surrounding(host, bytes.mutableSpan().data(), bytes.size(), &length, &cursor, &anchor, &state, &legacyToken);
    if (status != RV_OK || state != 1 || !legacyToken)
        return RV_ERR_UNSUPPORTED;
    return rv_host_ime_delete_surrounding(host, legacyToken, saved.origin + start, saved.origin + end);
}
