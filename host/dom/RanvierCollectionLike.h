// The setlike and maplike operations gen/domgen.py binds through gen/dom.json's setlikeBindings and
// maplikeBindings. Each reads and writes the engine's backing state in Web IDL iteration order: a set or map
// keeps the insertion position of an entry until the entry is deleted.
#pragma once

#include "AbstractRange.h"
#include "Highlight.h"
#include "HighlightRegistry.h"
#include <wtf/KeyValuePair.h>
#include <wtf/Vector.h>
#include <wtf/text/AtomString.h>

namespace WebCore {

struct RanvierCollectionLike {
    // Highlight: setlike<AbstractRange>.

    // new Highlight(...initialRanges): a range given more than once is added once, at its first position.
    static Ref<Highlight> createHighlight(Vector<Ref<AbstractRange>>&& initialRanges)
    {
        Vector<std::reference_wrapper<AbstractRange>> unique;
        for (auto& range : initialRanges) {
            if (!unique.containsIf([&](auto& existing) { return &existing.get() == range.ptr(); }))
                unique.append(range.get());
        }
        return Highlight::create(FixedVector<std::reference_wrapper<AbstractRange>> { WTF::move(unique) });
    }
    static uint32_t size(const Highlight& highlight) { return highlight.highlightRanges().size(); }
    static bool has(const Highlight& highlight, const AbstractRange& range)
    {
        return highlight.highlightRanges().containsIf([&](auto& entry) { return &entry->range() == &range; });
    }
    static Vector<Ref<AbstractRange>> values(const Highlight& highlight)
    {
        return WTF::map(highlight.highlightRanges(), [](auto& entry) { return Ref { entry->range() }; });
    }
    // A range already in the set keeps its position.
    static void add(Highlight& highlight, AbstractRange& range)
    {
        if (!has(highlight, range))
            highlight.addToSetLike(range);
    }
    static bool remove(Highlight& highlight, const AbstractRange& range) { return highlight.removeFromSetLike(range); }
    static void clear(Highlight& highlight) { highlight.clearFromSetLike(); }

    // HighlightRegistry: maplike<DOMString, Highlight>, in registration order.

    static uint32_t size(const HighlightRegistry& registry) { return registry.highlightNames().size(); }
    static bool has(const HighlightRegistry& registry, const AtomString& name) { return registry.map().contains(name); }
    static RefPtr<Highlight> get(const HighlightRegistry& registry, const AtomString& name) { return registry.map().get(name); }
    static Vector<KeyValuePair<String, Ref<Highlight>>> entries(const HighlightRegistry& registry)
    {
        return WTF::map(registry.highlightNames(), [&](auto& name) {
            return KeyValuePair<String, Ref<Highlight>> { name.string(), Ref { *registry.map().get(name) } };
        });
    }
    // Replacing the highlight of a registered name keeps the name's position and repaints both highlights.
    static void set(HighlightRegistry& registry, const AtomString& name, Highlight& highlight)
    {
        RefPtr replaced = registry.map().get(name);
        registry.setFromMapLike(AtomString { name }, Ref { highlight });
        if (replaced) {
            replaced->repaint();
            highlight.repaint();
        }
    }
    static bool remove(HighlightRegistry& registry, const AtomString& name) { return registry.remove(name); }
    // Unregisters every name and leaves each highlight's ranges in place.
    static void clear(HighlightRegistry& registry)
    {
        for (auto& name : Vector<AtomString> { registry.highlightNames() })
            registry.remove(name);
    }
};

} // namespace WebCore
