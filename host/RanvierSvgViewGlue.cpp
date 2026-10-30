#include "config.h"
#include "RanvierSvgViewGlue.h"
#include "Document.h"
#include "DocumentInlines.h"
#include "Node.h"
#include "SVGSVGElement.h"
#include "SVGElementTypeHelpers.h"
#include <wtf/MainThread.h>
#include <wtf/text/WTFString.h>

using namespace WebCore;

int32_t ranvier_host_select_svg_view(RvNode* handle, const char* fragment, int32_t* selected)
{
    if (!handle || !fragment || !selected)
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
    auto* document = dynamicDowncast<Document>(reinterpret_cast<Node*>(handle));
    if (!document || !document->isSVGDocument())
        return RV_ERR_UNSUPPORTED;
    RefPtr root = dynamicDowncast<SVGSVGElement>(document->documentElement());
    if (!root)
        return RV_ERR_UNSUPPORTED;
    auto value = String::fromUTF8(fragment);
    if (value.isNull())
        return RV_ERR_UNSUPPORTED;
    document->updateLayoutIgnorePendingStylesheets();
    root->resetScrollAnchor();
    *selected = !value.isEmpty() && root->scrollToFragment(value) ? 1 : 0;
    return RV_OK;
}
