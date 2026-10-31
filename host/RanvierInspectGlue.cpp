#include "config.h"
#include "RanvierInspectGlue.h"
#include "CSSSelector.h"
#include "CSSSelectorList.h"
#include "CSSSerializationContext.h"
#include "ContainerNodeInlines.h"
#include "Document.h"
#include "Element.h"
#include "ElementRuleCollector.h"
#include "FloatQuad.h"
#include "LocalFrame.h"
#include "RenderBox.h"
#include "RenderBoxInlines.h"
#include "RenderChildIterator.h"
#include "RenderElementInlines.h"
#include "RenderObjectInlines.h"
#include "RenderTreeAsText.h"
#include "RenderView.h"
#include "SelectorChecker.h"
#include "Settings.h"
#include "StyleProperties.h"
#include "StyleResolver.h"
#include "StyleRule.h"
#include "StyledElement.h"
#include "NodeInlines.h"
#include "ElementInlines.h"
#include <wtf/text/CString.h>
#include <wtf/text/TextStream.h>

using namespace WebCore;

namespace {

Document* documentOf(RvNode* handle)
{
    return handle ? dynamicDowncast<Document>(reinterpret_cast<Node*>(handle)) : nullptr;
}

// The element when it is connected to document.
Element* elementIn(Document& document, RvNode* handle)
{
    auto* element = handle ? dynamicDowncast<Element>(reinterpret_cast<Node*>(handle)) : nullptr;
    if (!element || &element->document() != &document || !element->isConnected())
        return nullptr;
    return element;
}

OptionSet<RenderAsTextFlag> renderAsTextFlags(int32_t flags)
{
    OptionSet<RenderAsTextFlag> result;
    if (flags & RV_RENDER_TREE_ALL_LAYERS)
        result.add(RenderAsTextFlag::ShowAllLayers);
    if (flags & RV_RENDER_TREE_LAYER_NESTING)
        result.add(RenderAsTextFlag::ShowLayerNesting);
    if (flags & RV_RENDER_TREE_OVERFLOW)
        result.add(RenderAsTextFlag::ShowOverflow);
    if (flags & RV_RENDER_TREE_SVG_GEOMETRY)
        result.add(RenderAsTextFlag::ShowSVGGeometry);
    if (flags & RV_RENDER_TREE_ID_AND_CLASS)
        result.add(RenderAsTextFlag::ShowIDAndClass);
    if (flags & RV_RENDER_TREE_LAYOUT_STATE)
        result.add(RenderAsTextFlag::ShowLayoutState);
    return result;
}

void writeSubtree(TextStream& stream, const RenderObject& renderer, OptionSet<RenderAsTextFlag> flags)
{
    stream << indent;
    RenderTreeAsText::writeRenderObject(stream, renderer, flags);
    stream << '\n';
    TextStream::IndentScope scope(stream);
    if (auto* element = dynamicDowncast<RenderElement>(renderer)) {
        for (auto& child : childrenOfType<RenderObject>(*element))
            writeSubtree(stream, child, flags);
    }
}

void sendText(RanvierInspectTextSink sink, void* context, const String& text)
{
    auto utf8 = text.utf8();
    sink(context, utf8.data(), static_cast<int32_t>(utf8.length()));
}

bool before(const std::array<uint8_t, 3>& left, const std::array<uint8_t, 3>& right)
{
    return std::lexicographical_compare(left.begin(), left.end(), right.begin(), right.end());
}

void sendRule(RanvierInspectRuleSink sink, void* context, int32_t origin, const StyleRule* rule, const StyleProperties* properties, Element& element)
{
    CString selectorText;
    CString matchedSelector;
    std::array<uint8_t, 3> specificity { };
    int32_t selectorCount = 0;
    int32_t matchedCount = 0;
    if (rule) {
        SelectorChecker checker(element.document());
        SelectorChecker::CheckingContext checking(SelectorChecker::Mode::CollectingRules);
        const CSSSelector* best = nullptr;
        for (auto& selector : rule->selectorList()) {
            ++selectorCount;
            if (!checker.match(selector, element, checking))
                continue;
            ++matchedCount;
            auto tuple = selector.computeSpecificityTuple();
            if (!best || before(specificity, tuple)) {
                best = &selector;
                specificity = tuple;
            }
        }
        selectorText = rule->selectorList().selectorsText().utf8();
        if (best)
            matchedSelector = best->selectorText().utf8();
    }
    auto declarations = properties->asText(CSS::defaultSerializationContext()).utf8();
    RanvierInspectRule entry {
        origin, { specificity[0], specificity[1], specificity[2] }, selectorCount, matchedCount,
        selectorText.data(), static_cast<int32_t>(selectorText.length()),
        matchedSelector.data(), static_cast<int32_t>(matchedSelector.length()),
        declarations.data(), static_cast<int32_t>(declarations.length())
    };
    sink(context, &entry);
}

}

int32_t ranvier_inspect_render_tree(RvNode* documentHandle, RvNode* target, int32_t flags, RanvierInspectTextSink sink, void* context)
{
    RefPtr document = documentOf(documentHandle);
    if (!document || !sink)
        return RV_ERR_NULL_ARGUMENT;
    auto options = renderAsTextFlags(flags);
    if (!target || target == documentHandle) {
        RefPtr frame = document->frame();
        if (!frame || !frame->contentRenderer())
            return RV_ERR_UNSUPPORTED;
        sendText(sink, context, externalRepresentation(frame.get(), options));
        return RV_OK;
    }
    RefPtr element = elementIn(*document, target);
    if (!element)
        return RV_ERR_UNSUPPORTED;
    document->updateLayoutIgnorePendingStylesheets();
    CheckedPtr renderer = element->renderer();
    if (!renderer || !document->renderView())
        return RV_ERR_UNSUPPORTED;
    auto stream = createTextStream(*document->renderView());
    writeSubtree(stream, *renderer, options);
    sendText(sink, context, stream.release());
    return RV_OK;
}

int32_t ranvier_inspect_matched_rules(RvNode* documentHandle, RvNode* elementHandle, RanvierInspectRuleSink sink, void* context)
{
    RefPtr document = documentOf(documentHandle);
    if (!document || !elementHandle || !sink)
        return RV_ERR_NULL_ARGUMENT;
    if (!is<Element>(*reinterpret_cast<Node*>(elementHandle)))
        return RV_ERR_NOT_ELEMENT;
    RefPtr element = elementIn(*document, elementHandle);
    if (!element)
        return RV_ERR_UNSUPPORTED;
    document->updateStyleIfNeeded();
    auto& resolver = element->styleResolver();
    Style::ElementRuleCollector collector(*element, resolver.ruleSets(), nullptr, SelectorChecker::Mode::CollectingRules);
    collector.setMedium(resolver.mediaQueryEvaluator());
    bool authorAndUser = document->settings().authorAndUserStylesEnabled();
    collector.matchUARules();
    size_t userAgentEnd = collector.matchedRuleList().size();
    if (authorAndUser)
        collector.matchUserRules();
    size_t userEnd = collector.matchedRuleList().size();
    if (authorAndUser)
        collector.matchAuthorRules();
    auto& rules = collector.matchedRuleList();
    // A rule appears once per matching selector; its last position, that of its most specific match, is kept.
    for (size_t index = 0; index < rules.size(); ++index) {
        bool later = false;
        for (size_t next = index + 1; next < rules.size() && !later; ++next)
            later = rules[next].ptr() == rules[index].ptr();
        if (later)
            continue;
        int32_t origin = index < userAgentEnd ? RV_RULE_ORIGIN_USER_AGENT : index < userEnd ? RV_RULE_ORIGIN_USER : RV_RULE_ORIGIN_AUTHOR;
        sendRule(sink, context, origin, rules[index].ptr(), &rules[index]->properties(), *element);
    }
    if (RefPtr styled = dynamicDowncast<StyledElement>(*element)) {
        if (auto* inlineStyle = styled->inlineStyle(); inlineStyle && !inlineStyle->isEmpty())
            sendRule(sink, context, RV_RULE_ORIGIN_INLINE, nullptr, inlineStyle, *element);
    }
    return RV_OK;
}

int32_t ranvier_inspect_box_model(RvNode* documentHandle, RvNode* elementHandle, double* values)
{
    RefPtr document = documentOf(documentHandle);
    if (!document || !elementHandle || !values)
        return RV_ERR_NULL_ARGUMENT;
    if (!is<Element>(*reinterpret_cast<Node*>(elementHandle)))
        return RV_ERR_NOT_ELEMENT;
    RefPtr element = elementIn(*document, elementHandle);
    if (!element)
        return RV_ERR_UNSUPPORTED;
    document->updateLayoutIgnorePendingStylesheets();
    CheckedPtr box = dynamicDowncast<RenderBox>(element->renderer());
    if (!box)
        return RV_ERR_UNSUPPORTED;
    LayoutRect border = box->borderBoxRect();
    LayoutRect padding { box->borderLeft(), box->borderTop(), border.width() - box->borderLeft() - box->borderRight(),
        border.height() - box->borderTop() - box->borderBottom() };
    LayoutRect content = box->contentBoxRect();
    LayoutRect margin { -box->marginLeft(), -box->marginTop(), border.width() + box->marginLeft() + box->marginRight(),
        border.height() + box->marginTop() + box->marginBottom() };
    LayoutRect rects[] = { content, padding, border, margin };
    double result[RV_BOX_VALUES];
    for (int index = 0; index < 4; ++index) {
        FloatRect rect = box->localToAbsoluteQuad(FloatQuad { FloatRect { rects[index] } }).boundingBox();
        document->convertAbsoluteToClientRect(rect, box->style());
        result[index * 4] = rect.x();
        result[index * 4 + 1] = rect.y();
        result[index * 4 + 2] = rect.width();
        result[index * 4 + 3] = rect.height();
    }
    std::copy(std::begin(result), std::end(result), values);
    return RV_OK;
}
