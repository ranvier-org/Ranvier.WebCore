#include "config.h"
#include "RanvierViewportGlue.h"
#include "Document.h"
#include "EventTarget.h"
#include "EventTargetInlines.h"
#include "EventTargetInterfaces.h"
#include "LocalDOMWindow.h"
#include "LocalFrame.h"
#include "LocalFrameView.h"
#include "MediaQueryList.h"
#include "Node.h"
#include "DocumentPage.h"
#include "Page.h"
#include "RenderBoxInlines.h"
#include "RenderObjectInlines.h"
#include "RenderView.h"
#include <cmath>
#include <cstring>

using namespace WebCore;

namespace {

Document* documentOf(RvNode* handle)
{
    return handle ? dynamicDowncast<Document>(reinterpret_cast<Node*>(handle)) : nullptr;
}

MediaQueryList* mediaQueryList(RvEventTarget* handle)
{
    auto* target = reinterpret_cast<EventTarget*>(handle);
    if (target->eventTargetInterface() != EventTargetInterfaceType::MediaQueryList)
        return nullptr;
    return static_cast<MediaQueryList*>(target);
}

}

int32_t ranvier_window_metrics(RvNode* documentHandle, RvWindowMetrics* metrics)
{
    RefPtr document = documentOf(documentHandle);
    if (!document || !metrics)
        return RV_ERR_NULL_ARGUMENT;
    RefPtr window = document->window();
    if (!window || !window->frame())
        return RV_ERR_PAINT_FAILED;
    metrics->innerWidth = window->innerWidth();
    metrics->innerHeight = window->innerHeight();
    metrics->devicePixelRatio = window->devicePixelRatio();
    return RV_OK;
}

RvEventTarget* ranvier_match_media(RvNode* documentHandle, const char* query)
{
    RefPtr document = documentOf(documentHandle);
    if (!document || !query)
        return nullptr;
    RefPtr window = document->window();
    if (!window)
        return nullptr;
    RefPtr list = window->matchMedia(String::fromUTF8(query));
    if (!list)
        return nullptr;
    EventTarget& target = *list;
    target.ref();
    return reinterpret_cast<RvEventTarget*>(&target);
}

void ranvier_page_set_display(RvNode* documentHandle, uint32_t displayID)
{
    RefPtr document = dynamicDowncast<Document>(reinterpret_cast<Node*>(documentHandle));
    if (!document || !document->page())
        return;
    document->page()->windowScreenDidChange(displayID, std::nullopt);
}

int32_t ranvier_media_query_matches(RvEventTarget* handle, int32_t* matches)
{
    if (!handle || !matches)
        return RV_ERR_NULL_ARGUMENT;
    RefPtr list = mediaQueryList(handle);
    if (!list)
        return RV_ERR_WRONG_INTERFACE;
    *matches = list->matches() ? 1 : 0;
    return RV_OK;
}

int32_t ranvier_media_query_media(RvEventTarget* handle, char* buffer, int32_t capacity, int32_t* length)
{
    if (!handle || !length)
        return RV_ERR_NULL_ARGUMENT;
    RefPtr list = mediaQueryList(handle);
    if (!list)
        return RV_ERR_WRONG_INTERFACE;
    auto bytes = list->media().utf8();
    *length = static_cast<int32_t>(bytes.length());
    if (!buffer || capacity < *length)
        return RV_ERR_BUFFER_TOO_SMALL;
    std::memcpy(buffer, bytes.data(), bytes.length());
    return RV_OK;
}

namespace {

enum class Space : int32_t { Node = RV_SPACE_NODE, Page = RV_SPACE_PAGE, Client = RV_SPACE_CLIENT, Host = RV_SPACE_HOST, Device = RV_SPACE_DEVICE };

struct Anchor {
    RefPtr<Node> node;
    RefPtr<LocalFrameView> view;
    RefPtr<Page> page;
};

bool isSpace(int32_t space)
{
    return space >= RV_SPACE_NODE && space <= RV_SPACE_DEVICE;
}

// RV_OK with the anchor's frame view, or the status for a node outside the document a live host shows.
int32_t anchorOf(RvNode* handle, Anchor& anchor)
{
    Ref node = *reinterpret_cast<Node*>(handle);
    Ref document = node->document();
    RefPtr frame = document->frame();
    if (!node->isConnected() || !frame || frame->document() != document.ptr() || !frame->page() || !frame->view())
        return RV_ERR_DETACHED;
    if (!frame->isMainFrame())
        return RV_ERR_UNSUPPORTED;
    anchor = { node.ptr(), frame->view(), frame->page() };
    return RV_OK;
}

// The CSS box of an RV_SPACE_NODE anchor: the render view for the document node.
RenderBox* boxOf(Node& node)
{
    if (auto* document = dynamicDowncast<Document>(node))
        return document->renderView();
    return dynamicDowncast<RenderBox>(node.renderer());
}

// Points in WebCore's absolute space: the main frame's contents, scaled by the page scale.
FloatPoint toAbsolute(Space space, const Anchor& anchor, RenderBox* box, FloatPoint point)
{
    auto& view = *anchor.view;
    switch (space) {
    case Space::Node:
        return box->localToAbsolute(point, MapCoordinatesMode::UseTransforms);
    case Space::Page:
        return point.scaled(view.documentToAbsoluteScaleFactor());
    case Space::Client:
        return view.clientToDocumentPoint(point).scaled(view.documentToAbsoluteScaleFactor());
    case Space::Device:
        point.scale(1 / anchor.page->deviceScaleFactor());
        [[fallthrough]];
    case Space::Host:
        return view.rootViewToContents(point);
    }
    return point;
}

std::optional<FloatPoint> fromAbsolute(Space space, const Anchor& anchor, RenderBox* box, FloatPoint point)
{
    auto& view = *anchor.view;
    switch (space) {
    case Space::Node: {
        auto local = box->absoluteToLocal(DoublePoint { point.x(), point.y() }, MapCoordinatesMode::UseTransforms);
        // A singular transform has no unique local point: the forward map collapses it or misses the target.
        auto origin = box->localToAbsolute(local, MapCoordinatesMode::UseTransforms);
        auto dx = box->localToAbsolute(local + FloatSize(1, 0), MapCoordinatesMode::UseTransforms) - origin;
        auto dy = box->localToAbsolute(local + FloatSize(0, 1), MapCoordinatesMode::UseTransforms) - origin;
        double determinant = static_cast<double>(dx.width()) * dy.height() - static_cast<double>(dx.height()) * dy.width();
        if (!(std::abs(determinant) > 1e-6) || !(std::hypot(origin.x() - point.x(), origin.y() - point.y()) <= 1. / 64))
            return std::nullopt;
        return local;
    }
    case Space::Page:
        return view.absoluteToDocumentPoint(point);
    case Space::Client:
        return view.documentToClientPoint(view.absoluteToDocumentPoint(point));
    case Space::Host:
        return view.contentsToRootView(point);
    case Space::Device:
        return view.contentsToRootView(point).scaled(anchor.page->deviceScaleFactor());
    }
    return std::nullopt;
}

// Resolves both anchors with layout updated: RV_OK, or the status every conversion returns.
int32_t resolve(RvNode* from, int32_t fromSpace, RvNode* to, int32_t toSpace, Anchor& source, Anchor& target, RenderBox*& sourceBox, RenderBox*& targetBox)
{
    if (!from)
        return RV_ERR_NULL_ARGUMENT;
    if (!isSpace(fromSpace) || !isSpace(toSpace))
        return RV_ERR_UNSUPPORTED;
    if (auto status = anchorOf(from, source))
        return status;
    if (auto status = anchorOf(to ? to : reinterpret_cast<RvNode*>(&source.node->document()), target))
        return status;
    if (source.page != target.page)
        return RV_ERR_WRONG_HOST;
    protect(source.node->document())->updateLayoutIgnorePendingStylesheets();
    // Layout can replace the anchors' boxes, so they are read after it.
    sourceBox = fromSpace == RV_SPACE_NODE ? boxOf(*source.node) : nullptr;
    targetBox = toSpace == RV_SPACE_NODE ? boxOf(*target.node) : nullptr;
    if ((fromSpace == RV_SPACE_NODE && !sourceBox) || (toSpace == RV_SPACE_NODE && !targetBox))
        return RV_ERR_UNSUPPORTED;
    return RV_OK;
}

int32_t convert(const Anchor& source, Space fromSpace, RenderBox* sourceBox, const Anchor& target, Space toSpace, RenderBox* targetBox, std::span<double> xy)
{
    Vector<double> result(xy.size());
    for (size_t index = 0; index < xy.size(); index += 2) {
        if (!std::isfinite(xy[index]) || !std::isfinite(xy[index + 1]))
            return RV_ERR_UNSUPPORTED;
        auto absolute = toAbsolute(fromSpace, source, sourceBox, FloatPoint(xy[index], xy[index + 1]));
        auto point = fromAbsolute(toSpace, target, targetBox, absolute);
        if (!point)
            return RV_ERR_UNSUPPORTED;
        result[index] = point->x();
        result[index + 1] = point->y();
    }
    std::ranges::copy(result, xy.begin());
    return RV_OK;
}

}

int32_t ranvier_convert_points(RvNode* from, int32_t fromSpace, RvNode* to, int32_t toSpace, double* xy, int32_t count)
{
    if (from && count > 0 && !xy)
        return RV_ERR_NULL_ARGUMENT;
    Anchor source, target;
    RenderBox* sourceBox = nullptr;
    RenderBox* targetBox = nullptr;
    if (auto status = resolve(from, fromSpace, to, toSpace, source, target, sourceBox, targetBox))
        return status;
    if (count < 0)
        return RV_ERR_UNSUPPORTED;
    if (!count)
        return RV_OK;
    return convert(source, static_cast<Space>(fromSpace), sourceBox, target, static_cast<Space>(toSpace), targetBox, std::span<double>(xy, static_cast<size_t>(count) * 2));
}

int32_t ranvier_box_quad(RvNode* node, int32_t box, RvNode* to, int32_t toSpace, double* quad)
{
    if (node && !quad)
        return RV_ERR_NULL_ARGUMENT;
    Anchor source, target;
    RenderBox* sourceBox = nullptr;
    RenderBox* targetBox = nullptr;
    if (auto status = resolve(node, RV_SPACE_NODE, to, toSpace, source, target, sourceBox, targetBox))
        return status;
    LayoutRect rect = sourceBox->borderBoxRect();
    switch (box) {
    case RV_QUAD_BORDER_BOX:
        break;
    case RV_QUAD_PADDING_BOX:
        rect = { LayoutUnit(sourceBox->borderLeft()), LayoutUnit(sourceBox->borderTop()), rect.width() - sourceBox->borderLeft() - sourceBox->borderRight(), rect.height() - sourceBox->borderTop() - sourceBox->borderBottom() };
        break;
    case RV_QUAD_CONTENT_BOX:
        rect = sourceBox->contentBoxRect();
        break;
    case RV_QUAD_MARGIN_BOX:
        rect = { -sourceBox->marginLeft(), -sourceBox->marginTop(), rect.width() + sourceBox->marginLeft() + sourceBox->marginRight(), rect.height() + sourceBox->marginTop() + sourceBox->marginBottom() };
        break;
    default:
        return RV_ERR_UNSUPPORTED;
    }
    FloatRect corners = rect;
    double points[8] = { corners.x(), corners.y(), corners.maxX(), corners.y(), corners.maxX(), corners.maxY(), corners.x(), corners.maxY() };
    if (auto status = convert(source, Space::Node, sourceBox, target, static_cast<Space>(toSpace), targetBox, std::span<double>(points)))
        return status;
    std::copy(std::begin(points), std::end(points), quad);
    return RV_OK;
}
