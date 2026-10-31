// Host checks for Web Animations custom effects (A09): a CustomEffectCallback belongs to the document it was
// created for, and a receiver of another document returns RV_ERR_WRONG_HOST.
#pragma once

#include "ContextDestructionObserverInlines.h"
#include "CustomEffectCallback.h"
#include "Document.h"
#include "DocumentTimeline.h"

namespace Ranvier {

inline bool customEffectCallbackMatches(WebCore::CustomEffectCallback& callback, WebCore::Document& document)
{
    return callback.scriptExecutionContext() == &document;
}

inline bool customEffectCallbackMatches(WebCore::CustomEffectCallback& callback, WebCore::DocumentTimeline& timeline)
{
    auto* document = timeline.document();
    return document && callback.scriptExecutionContext() == document;
}

} // namespace Ranvier
