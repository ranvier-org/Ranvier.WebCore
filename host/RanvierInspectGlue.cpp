#include "config.h"
#include "RanvierInspectGlue.h"
#include "CSSConditionRule.h"
#include "CSSContainerRule.h"
#include "CSSCustomPropertyValue.h"
#include "CSSImportRule.h"
#include "CSSKeywordValueInlines.h"
#include "CSSLayerBlockRule.h"
#include "CSSMediaRule.h"
#include "CSSProperty.h"
#include "CSSPropertyNames.h"
#include "CSSPropertyParser.h"
#include "CSSSelector.h"
#include "CSSStyleRule.h"
#include "CSSStyleSheet.h"
#include "CSSSupportsRule.h"
#include "MatchResult.h"
#include "PropertyCascade.h"
#include "StyleCustomPropertyRegistry.h"
#include "StyleScope.h"
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

namespace {

struct RuleSelectors {
    CString selectorText;
    CString matchedSelector;
    std::array<uint8_t, 3> specificity { };
};

// The selectors of a rule from the tree scope at ordinal, matched as the collector matches them: :host() against the
// element's shadow tree, ::slotted() against its slot and ::part() from the host's tree.
RuleSelectors selectorsOf(const StyleRule& rule, Element& element, WebCore::Style::ScopeOrdinal ordinal)
{
    RuleSelectors result;
    SelectorChecker checker(element.document());
    SelectorChecker::CheckingContext checking(SelectorChecker::Mode::CollectingRules);
    checking.styleScopeOrdinal = ordinal;
    const CSSSelector* best = nullptr;
    for (auto& selector : rule.selectorList()) {
        if (!checker.match(selector, element, checking))
            continue;
        auto tuple = selector.computeSpecificityTuple();
        if (!best || before(result.specificity, tuple)) {
            best = &selector;
            result.specificity = tuple;
        }
    }
    result.selectorText = rule.selectorList().selectorsText().utf8();
    if (best)
        result.matchedSelector = best->selectorText().utf8();
    return result;
}

struct RuleLocation {
    int32_t sheet { -1 };
    int32_t rule { -1 };
    String layer;
    String conditions;
};

// Locations of the style rules of a tree scope's active sheets, keyed by declaration block.
class RuleLocations {
public:
    RuleLocations() = default;
    explicit RuleLocations(const WebCore::Style::Scope& scope)
    {
        int32_t sheetIndex = 0;
        for (auto& sheet : scope.activeStyleSheets()) {
            m_sheet = sheetIndex++;
            m_rule = 0;
            visitChildren(sheet.get(), { }, { });
        }
    }

    const RuleLocation* find(const StyleRule& rule) const
    {
        if (auto iterator = m_locations.find(&rule); iterator != m_locations.end())
            return &iterator->value;
        // A rule the rule set copied from its sheet, such as a nested rule, shares its declaration block.
        auto iterator = m_byProperties.find(&rule.properties());
        return iterator == m_byProperties.end() || !iterator->value ? nullptr : &m_locations.find(iterator->value)->value;
    }

private:
    template<typename Container> void visitChildren(Container& container, const String& layer, const String& conditions)
    {
        for (unsigned index = 0; index < container.length(); ++index) {
            if (RefPtr rule = container.item(index))
                visit(*rule, layer, conditions);
        }
    }

    static String joinLayer(const String& outer, const String& name)
    {
        return outer.isNull() ? name : makeString(outer, '.', name);
    }

    static String joinCondition(const String& outer, ASCIILiteral keyword, const String& text)
    {
        auto line = makeString(keyword, ' ', text);
        return outer.isEmpty() ? line : makeString(outer, '\n', line);
    }

    void visit(CSSRule& rule, const String& layer, const String& conditions)
    {
        if (auto* style = dynamicDowncast<CSSStyleRule>(rule)) {
            auto& styleRule = style->styleRule();
            m_locations.add(&styleRule, RuleLocation { m_sheet, m_rule++, layer, conditions });
            // A declaration block held by several rules locates none of them.
            auto added = m_byProperties.add(&styleRule.properties(), &styleRule);
            if (!added.isNewEntry)
                added.iterator->value = nullptr;
            visitChildren(*style, layer, conditions);
        } else if (auto* block = dynamicDowncast<CSSLayerBlockRule>(rule))
            visitChildren(*block, joinLayer(layer, block->name()), conditions);
        else if (auto* group = dynamicDowncast<CSSGroupingRule>(rule)) {
            if (auto* condition = dynamicDowncast<CSSConditionRule>(*group)) {
                auto keyword = is<CSSMediaRule>(rule) ? "@media"_s : is<CSSSupportsRule>(rule) ? "@supports"_s : "@container"_s;
                visitChildren(*group, layer, joinCondition(conditions, keyword, condition->conditionText()));
            } else
                visitChildren(*group, layer, conditions);
        }
        else if (auto* import = dynamicDowncast<CSSImportRule>(rule)) {
            if (RefPtr imported = import->styleSheet()) {
                auto name = import->layerName();
                visitChildren(*imported, name.isNull() ? layer : joinLayer(layer, name), conditions);
            }
        }
    }

    HashMap<const StyleRule*, RuleLocation> m_locations;
    HashMap<const StyleProperties*, const StyleRule*> m_byProperties;
    int32_t m_sheet { -1 };
    int32_t m_rule { 0 };
};

struct CascadeQuery {
    CSSPropertyID id { CSSPropertyInvalid };
    AtomString customName;
    bool isCustom() const { return id == CSSPropertyCustom; }
};

struct CascadeLevel {
    struct Entry {
        RanvierCascadeEntry fields { };
        std::array<CString, RV_CASCADE_STRING_FIELDS> strings;
        const CSSValue* value { nullptr };
        WebCore::Style::CascadeLayerPriority layerPriority { 0 };
    };
    Vector<Entry> entries;
    const CSSValue* winner { nullptr };
};

bool declares(const CascadeQuery& query, const StyleProperties::PropertyReference& property, CSSPropertyID counterpart)
{
    if (query.isCustom()) {
        auto* custom = dynamicDowncast<CSSCustomPropertyValue>(property.value());
        return property.id() == CSSPropertyCustom && custom && custom->name() == query.customName;
    }
    return property.id() == query.id || (counterpart != CSSPropertyInvalid && property.id() == counterpart);
}

const CSSValue* cascadeWinner(const WebCore::Style::PropertyCascade& cascade, const CascadeQuery& query, WritingMode writingMode)
{
    if (query.isCustom())
        return cascade.hasCustomProperty(query.customName) ? cascade.customProperty(query.customName).cssValue[0] : nullptr;
    if (CSSProperty::isInLogicalPropertyGroup(query.id)) {
        auto* property = cascade.lastPropertyResolvingLogicalPropertyPair(query.id, writingMode);
        return property ? property->cssValue[0] : nullptr;
    }
    return cascade.hasNormalProperty(query.id) ? cascade.normalProperty(query.id).cssValue[0] : nullptr;
}

CascadeLevel cascadeLevel(Element& element, const CascadeQuery& query, int32_t depth)
{
    auto& resolver = element.styleResolver();
    bool authorAndUser = element.document().settings().authorAndUserStylesEnabled();

    // Declaration blocks of the matching style rules.
    WebCore::Style::ElementRuleCollector rulesCollector(element, resolver.ruleSets(), nullptr, SelectorChecker::Mode::CollectingRules);
    rulesCollector.setMedium(resolver.mediaQueryEvaluator());
    rulesCollector.matchUARules();
    size_t userAgentEnd = rulesCollector.matchedRuleList().size();
    if (authorAndUser)
        rulesCollector.matchUserRules();
    size_t userEnd = rulesCollector.matchedRuleList().size();
    if (authorAndUser)
        rulesCollector.matchAuthorRules();
    auto& matchedRules = rulesCollector.matchedRuleList();

    WebCore::Style::ElementRuleCollector collector(element, resolver.ruleSets(), nullptr);
    collector.setMedium(resolver.mediaQueryEvaluator());
    collector.matchAllRules(authorAndUser, true);
    auto& matchResult = collector.matchResult();
    // Locations by the tree scope holding the rule: the element's, or its shadow tree's, slot's or host's.
    HashMap<const WebCore::Style::Scope*, RuleLocations> locations;
    auto locate = [&](const StyleRule& rule, WebCore::Style::ScopeOrdinal ordinal) -> const RuleLocation* {
        auto* scope = WebCore::Style::Scope::forOrdinal(element, ordinal);
        if (!scope)
            return nullptr;
        return locations.ensure(scope, [&] { return RuleLocations(*scope); }).iterator->value.find(rule);
    };

    WritingMode writingMode;
    if (auto* style = element.existingComputedStyle())
        writingMode = style->writingMode();
    auto counterpart = CSSPropertyInvalid;
    if (!query.isCustom() && CSSProperty::isInLogicalPropertyGroup(query.id)) {
        counterpart = CSSProperty::isDirectionAwareProperty(query.id) ? CSSProperty::resolveDirectionAwareProperty(query.id, writingMode)
            : CSSProperty::unresolvePhysicalProperty(query.id, writingMode);
        if (counterpart == query.id)
            counterpart = CSSPropertyInvalid;
    }

    CascadeLevel level;
    auto addDeclarations = [&](const Vector<WebCore::Style::MatchedProperties>& declarations, int32_t baseOrigin, size_t rulesBegin, size_t rulesEnd) {
        // The rule of each matched declaration block: the collected rules are in the same order, without hints and
        // inline style.
        Vector<const StyleRule*> ruleOf(declarations.size(), [](size_t) -> const StyleRule* { return nullptr; });
        size_t cursor = rulesBegin;
        for (size_t index = 0; index < declarations.size(); ++index) {
            if (declarations[index].fromStyleAttribute == WebCore::Style::FromStyleAttribute::Yes || cursor >= rulesEnd)
                continue;
            if (&matchedRules[cursor]->properties() == declarations[index].properties.ptr())
                ruleOf[index] = matchedRules[cursor++].ptr();
        }
        for (size_t index = 0; index < declarations.size(); ++index) {
            auto& matched = declarations[index];
            if (matched.isStartingStyle == WebCore::Style::IsStartingStyle::Yes)
                continue;
            auto* rule = ruleOf[index];
            // A rule matching through several selectors appears once per selector; the last position is the cascade's.
            bool later = false;
            for (size_t next = index + 1; rule && next < declarations.size() && !later; ++next)
                later = ruleOf[next] == rule;
            if (later)
                continue;
            auto& properties = matched.properties.get();
            int32_t origin = baseOrigin;
            if (matched.fromStyleAttribute == WebCore::Style::FromStyleAttribute::Yes)
                origin = RV_RULE_ORIGIN_INLINE;
            else if (!rule && baseOrigin == RV_RULE_ORIGIN_AUTHOR)
                origin = RV_RULE_ORIGIN_PRESENTATIONAL_HINT;
            std::optional<RuleSelectors> selectors;
            for (unsigned position = 0; position < properties.propertyCount(); ++position) {
                auto property = properties.propertyAt(position);
                if (!declares(query, property, counterpart))
                    continue;
                if (rule && !selectors)
                    selectors = selectorsOf(*rule, element, matched.styleScopeOrdinal);
                CascadeLevel::Entry entry;
                auto& numbers = entry.fields.numbers;
                numbers[RV_CASCADE_ORIGIN] = origin;
                if (selectors) {
                    for (int part = 0; part < 3; ++part)
                        numbers[RV_CASCADE_SPECIFICITY_A + part] = selectors->specificity[part];
                    entry.strings[RV_CASCADE_SELECTOR_TEXT] = selectors->selectorText;
                    entry.strings[RV_CASCADE_MATCHED_SELECTOR] = selectors->matchedSelector;
                }
                numbers[RV_CASCADE_IMPORTANT] = property.isImportant();
                bool layered = origin != RV_RULE_ORIGIN_INLINE && origin != RV_RULE_ORIGIN_PRESENTATIONAL_HINT
                    && matched.cascadeLayerPriority != WebCore::Style::RuleSet::cascadeLayerPriorityForUnlayered
                    && matched.cascadeLayerPriority != WebCore::Style::RuleSet::cascadeLayerPriorityForPresentationalHints;
                numbers[RV_CASCADE_LAYER_ORDER] = layered ? matched.cascadeLayerPriority - WebCore::Style::RuleSet::cascadeLayerPriorityForPresentationalHints - 1 : -1;
                numbers[RV_CASCADE_DEPTH] = depth;
                auto* location = rule ? locate(*rule, matched.styleScopeOrdinal) : nullptr;
                numbers[RV_CASCADE_SHEET_INDEX] = location ? location->sheet : -1;
                numbers[RV_CASCADE_RULE_INDEX] = location ? location->rule : -1;
                numbers[RV_CASCADE_DECLARATION_INDEX] = position;
                auto* value = property.value();
                bool substitution = value->hasSubstitutionFunctions();
                if (auto* custom = dynamicDowncast<CSSCustomPropertyValue>(*value))
                    substitution = custom->isVariableReference();
                numbers[RV_CASCADE_VARIABLE_REFERENCE] = substitution;
                entry.strings[RV_CASCADE_PROPERTY] = (property.id() == CSSPropertyCustom ? query.customName.string() : nameString(property.id()).string()).utf8();
                entry.strings[RV_CASCADE_VALUE] = value->cssText(CSS::defaultSerializationContext()).utf8();
                if (auto shorthand = property.shorthandID(); shorthand != CSSPropertyInvalid)
                    entry.strings[RV_CASCADE_SHORTHAND] = nameString(shorthand).string().utf8();
                if (location && layered)
                    entry.strings[RV_CASCADE_LAYER] = location->layer.utf8();
                if (location)
                    entry.strings[RV_CASCADE_CONDITIONS] = location->conditions.utf8();
                entry.value = value;
                entry.layerPriority = matched.cascadeLayerPriority;
                level.entries.append(WTF::move(entry));
            }
        }
    };
    addDeclarations(matchResult.userAgentDeclarations, RV_RULE_ORIGIN_USER_AGENT, 0, userAgentEnd);
    addDeclarations(matchResult.userDeclarations, RV_RULE_ORIGIN_USER, userAgentEnd, userEnd);
    addDeclarations(matchResult.authorDeclarations, RV_RULE_ORIGIN_AUTHOR, userEnd, matchedRules.size());

    auto cascade = makeUnique<WebCore::Style::PropertyCascade>(matchResult, WebCore::Style::PropertyCascade::normalProperties());
    level.winner = cascadeWinner(*cascade, query, writingMode);
    // Rules sharing a declaration block share its value: the cascade applies a normal declaration last at its last
    // position, and an important one last in its earliest layer.
    CascadeLevel::Entry* winner = nullptr;
    for (auto& entry : level.entries) {
        if (!level.winner || entry.value != level.winner)
            continue;
        if (!winner || !entry.fields.numbers[RV_CASCADE_IMPORTANT] || entry.layerPriority <= winner->layerPriority)
            winner = &entry;
    }
    if (winner)
        winner->fields.numbers[RV_CASCADE_WINNER] = 1;
    return level;
}

// The level's winner is inherit, or unset on an inherited property; a level without a winner inherits an inherited property.
bool inheritsFromParent(const CascadeLevel& level, bool inherited)
{
    if (!level.winner)
        return inherited;
    if (auto* custom = dynamicDowncast<CSSCustomPropertyValue>(*level.winner)) {
        auto keyword = custom->tryCSSWideKeyword();
        return keyword == CSSWideKeyword::Inherit || (keyword == CSSWideKeyword::Unset && inherited);
    }
    auto keyword = valueID(*level.winner);
    return keyword == CSSValueInherit || (keyword == CSSValueUnset && inherited);
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
    WebCore::Style::ElementRuleCollector collector(*element, resolver.ruleSets(), nullptr, SelectorChecker::Mode::CollectingRules);
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

int32_t ranvier_inspect_cascade(RvNode* documentHandle, RvNode* elementHandle, const uint8_t* property, int32_t propertyLength, RanvierInspectTextSink textSink, RanvierCascadeSink sink, void* context)
{
    RefPtr document = documentOf(documentHandle);
    if (!document || !elementHandle || !property || !textSink || !sink)
        return RV_ERR_NULL_ARGUMENT;
    if (!is<Element>(*reinterpret_cast<Node*>(elementHandle)))
        return RV_ERR_NOT_ELEMENT;
    RefPtr element = elementIn(*document, elementHandle);
    if (!element || propertyLength < 0)
        return RV_ERR_UNSUPPORTED;
    auto name = String::fromUTF8(std::span { reinterpret_cast<const char8_t*>(property), static_cast<size_t>(propertyLength) });
    if (name.isNull())
        return RV_ERR_UNSUPPORTED;
    // The pending style sheet changes the next style update applies, @property registrations included; element styles stay as they are.
    for (RefPtr<Element> scopeElement = element; scopeElement;) {
        auto& scope = WebCore::Style::Scope::forNode(*scopeElement);
        if (scope.hasPendingUpdate())
            scope.flushPendingUpdate();
        RefPtr shadowRoot = scopeElement->containingShadowRoot();
        scopeElement = shadowRoot ? shadowRoot->host() : nullptr;
    }
    CascadeQuery query;
    bool inherited;
    if (isCustomPropertyName(name)) {
        query.id = CSSPropertyCustom;
        query.customName = AtomString { name };
        inherited = WebCore::Style::Scope::forNode(*element).customPropertyRegistry().isInherited(query.customName);
    } else {
        query.id = cssPropertyID(name);
        if (query.id == CSSPropertyInvalid || isShorthand(query.id) || !isExposed(query.id, &document->settings()))
            return RV_ERR_UNSUPPORTED;
        inherited = CSSProperty::isInheritedProperty(query.id);
    }
    sendText(textSink, context, query.isCustom() ? query.customName.string() : nameString(query.id).string());
    int32_t depth = 0;
    for (RefPtr current = element; current; current = current->parentElementInComposedTree(), ++depth) {
        auto level = cascadeLevel(*current, query, depth);
        for (auto& entry : level.entries) {
            for (int field = 0; field < RV_CASCADE_STRING_FIELDS; ++field) {
                entry.fields.strings[field] = entry.strings[field].data();
                entry.fields.lengths[field] = static_cast<int32_t>(entry.strings[field].length());
            }
            sink(context, &entry.fields);
        }
        if (!inheritsFromParent(level, inherited))
            break;
    }
    return RV_OK;
}
