#pragma once

#include "ContextDestructionObserverInlines.h"
#include "Document.h"
#include "JSViewTransitionUpdateCallback.h"
#include "Settings.h"
#include "StartViewTransitionOptions.h"
#include "ViewTransition.h"
#include "ViewTransitionTypeSet.h"
#include "ViewTransitionUpdateCallback.h"

namespace Ranvier {

struct ViewTransitionOptions {
    RefPtr<WebCore::ViewTransitionUpdateCallback> update;
    std::optional<Vector<String>> types;
};

inline RefPtr<WebCore::ViewTransition> startViewTransition(WebCore::Document& document, ViewTransitionOptions&& options)
{
    WebCore::StartViewTransitionOptions engine;
    engine.update = WTF::move(options.update);
    if (options.types)
        engine.types = WTF::map(*options.types, [](auto& type) { return AtomString { type }; });
    return document.startViewTransition(WTF::move(engine));
}

inline bool viewTransitionsSupported(WebCore::Document& document)
{
#if USE(GPU_STUB)
    UNUSED_PARAM(document);
    return false;
#else
    return document.settings().acceleratedCompositingEnabled();
#endif
}

}

namespace WebCore {

struct RanvierViewTransitions {
    static uint32_t size(const ViewTransitionTypeSet& types) { return types.types().size(); }
    static bool has(const ViewTransitionTypeSet& types, const AtomString& value) { return types.hasType(value); }
    static Vector<String> values(const ViewTransitionTypeSet& types)
    {
        return WTF::map(types.types(), [](auto& type) { return type.string(); });
    }
    static void add(ViewTransitionTypeSet& types, const AtomString& value) { types.addToSetLike(value); }
    static bool remove(ViewTransitionTypeSet& types, const AtomString& value) { return types.removeFromSetLike(value); }
    static void clear(ViewTransitionTypeSet& types) { types.clearFromSetLike(); }
};

}
