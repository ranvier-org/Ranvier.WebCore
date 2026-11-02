#include "config.h"
#include "RanvierPrintGlue.h"
#include <memory>
#include <vector>
#include <wtf/MainThread.h>

#ifndef RANVIER_ENABLE_PDF
#define RANVIER_ENABLE_PDF 0
#endif

#if USE(SKIA) && RANVIER_ENABLE_PDF
#include "CSSUnits.h"
#include "Document.h"
#include "DocumentView.h"
#include "FrameDestructionObserverInlines.h"
#include "GraphicsContextSkia.h"
#include "LocalFrame.h"
#include "LocalFrameView.h"
#include "Node.h"
#include "PrintContext.h"
#include "RenderView.h"
#include "RenderingMode.h"
#include <cmath>
#include <include/core/SkCanvas.h>
#include <include/core/SkDocument.h>
#include <include/core/SkStream.h>
#include <include/docs/SkPDFDocument.h>
#include <include/docs/SkPDFJpegHelpers.h>
#endif

struct RvPrintPdfData {
    std::vector<uint8_t> bytes;
    int32_t pageCount { 0 };
    bool cancelled { false };
};

#if USE(SKIA) && RANVIER_ENABLE_PDF
namespace {
using namespace WebCore;

class BoundedStream final : public SkWStream {
public:
    explicit BoundedStream(uint64_t budget)
        : m_budget(budget) { }
    bool write(const void* data, size_t count) final
    {
        if (m_failed || count > m_budget - m_bytes.size()) {
            m_failed = true;
            return false;
        }
        if (count) {
            auto* first = static_cast<const uint8_t*>(data);
            m_bytes.insert(m_bytes.end(), first, first + count);
        }
        return true;
    }
    size_t bytesWritten() const final { return m_bytes.size(); }
    bool failed() const { return m_failed; }
    std::vector<uint8_t> take() { return std::move(m_bytes); }

private:
    uint64_t m_budget;
    bool m_failed { false };
    std::vector<uint8_t> m_bytes;
};

class PrintGuard {
public:
    explicit PrintGuard(LocalFrame& frame)
        : m_context(PrintContext::create(&frame))
        , m_view(*frame.view())
        , m_scroll(m_view->scrollPosition()) { }
    ~PrintGuard()
    {
        if (m_begun) {
            m_context->end();
            m_view->setScrollPosition(m_scroll);
        }
    }
    PrintContext& context() { return m_context; }
    void begin(float width, float height)
    {
        m_begun = true;
        m_context->begin(width, height);
    }

private:
    Ref<PrintContext> m_context;
    Ref<LocalFrameView> m_view;
    ScrollPosition m_scroll;
    bool m_begun { false };
};

bool valid(const RvPrintOptions& options)
{
    if (options.reserved || !options.max_pages || options.max_pages > 4096)
        return false;
    for (double value : { options.paper_width_points, options.paper_height_points,
             options.margin_top_points, options.margin_right_points,
             options.margin_bottom_points, options.margin_left_points }) {
        if (!std::isfinite(value) || value < 0 || value > 14400)
            return false;
    }
    return options.paper_width_points - options.margin_left_points - options.margin_right_points >= 1
        && options.paper_height_points - options.margin_top_points - options.margin_bottom_points >= 1
        && options.output_budget_bytes && options.output_budget_bytes <= 64 * 1024 * 1024
        && std::isfinite(options.raster_dpi) && options.raster_dpi >= 72 && options.raster_dpi <= 600;
}

int32_t paint(Document& document, LocalFrame& frame, const RvPrintOptions& options,
    RvPrintCancelPoll cancel, void* cancelContext, RvPrintPdfData& result)
{
    auto cancelled = [&] { return cancel && cancel(cancelContext); };
    if (cancelled()) {
        result.cancelled = true;
        return RV_OK;
    }
    PrintGuard guard(frame);
    auto& context = guard.context();
    FloatBoxExtent margins(static_cast<float>(options.margin_top_points), static_cast<float>(options.margin_right_points),
        static_cast<float>(options.margin_bottom_points), static_cast<float>(options.margin_left_points));
    auto effectiveMargins = context.computedPageMargin(margins);
    FloatSize available(options.paper_width_points - margins.left() - margins.right(),
        options.paper_height_points - margins.top() - margins.bottom());
    auto pageSize = context.computedPageSize(available, margins);
    if (!std::isfinite(pageSize.width()) || !std::isfinite(pageSize.height()) || pageSize.width() < 1 || pageSize.height() < 1)
        return RV_ERR_UNSUPPORTED;
    auto layoutInputScale = static_cast<float>(CSS::pixelsPerPt / PrintContext::minimumShrinkFactor());
    guard.begin(pageSize.width() * layoutInputScale, pageSize.height() * layoutInputScale);
    if (document.frame() != &frame || !frame.view() || !document.renderView())
        return RV_ERR_DETACHED;
    auto& view = *document.renderView();
    if (!view.writingMode().isHorizontal())
        return RV_ERR_UNSUPPORTED;
    auto documentRect = view.documentRect();
    auto layoutPageSize = frame.resizePageRectsKeepingRatio(pageSize, FloatSize(documentRect.size()));
    if (layoutPageSize.height() < 1 || std::ceil(documentRect.height() / layoutPageSize.height()) > options.max_pages)
        return RV_ERR_UNSUPPORTED;
    float pageHeight = 0;
    context.computePageRects(FloatRect(FloatPoint(), pageSize), 0, 0, 1, pageHeight, false);
    if (!context.pageCount() || context.pageCount() > options.max_pages)
        return RV_ERR_UNSUPPORTED;
    result.pageCount = context.pageCount();
    BoundedStream stream(options.output_budget_bytes);
    auto metadata = SkPDF::JPEG::MetadataWithCallbacks();
    metadata.fRasterDPI = options.raster_dpi;
    auto pdf = SkPDF::MakeDocument(&stream, metadata);
    if (!pdf)
        return RV_ERR_PAINT_FAILED;
    for (size_t index = 0; index < context.pageCount(); ++index) {
        if (cancelled()) {
            result.cancelled = true;
            pdf->abort();
            return RV_OK;
        }
        auto* canvas = pdf->beginPage(options.paper_width_points, options.paper_height_points);
        if (!canvas) {
            pdf->abort();
            return RV_ERR_PAINT_FAILED;
        }
        canvas->save();
        canvas->translate(effectiveMargins.left(), effectiveMargins.top());
        canvas->clipRect(SkRect::MakeWH(pageSize.width(), pageSize.height()));
        {
            GraphicsContextSkia graphics(*canvas, RenderingMode::PDFDocument, RenderingPurpose::Unspecified);
            context.spoolPage(graphics, static_cast<int>(index), pageSize.width());
        }
        canvas->restore();
        pdf->endPage();
        if (stream.failed()) {
            pdf->abort();
            return RV_ERR_PAINT_FAILED;
        }
    }
    pdf->close();
    if (stream.failed())
        return RV_ERR_PAINT_FAILED;
    result.bytes = stream.take();
    return result.bytes.empty() ? RV_ERR_PAINT_FAILED : RV_OK;
}
}
#endif

extern "C" int32_t ranvier_print_pdf_supported()
{
#if USE(SKIA) && RANVIER_ENABLE_PDF
    return 1;
#else
    return 0;
#endif
}

extern "C" int32_t ranvier_print_pdf(RvNode* handle, const RvPrintOptions* input,
    RvPrintCancelPoll cancel, void* cancelContext, RvPrintPdfData** output)
{
    if (output)
        *output = nullptr;
    if (!handle || !input || !output)
        return RV_ERR_NULL_ARGUMENT;
    if (!WTF::isMainThread())
        return RV_ERR_WRONG_THREAD;
#if USE(SKIA) && RANVIER_ENABLE_PDF
    if (input->size != sizeof(RvPrintOptions) || !valid(*input))
        return RV_ERR_UNSUPPORTED;
    auto* candidate = WTF::dynamicDowncast<WebCore::Document>(reinterpret_cast<WebCore::Node*>(handle));
    if (!candidate || !candidate->frame() || !candidate->frame()->view() || candidate->printing())
        return RV_ERR_DETACHED;
    Ref document = *candidate;
    Ref frame = *document->frame();
    auto result = std::make_unique<RvPrintPdfData>();
    auto status = paint(document, frame, *input, cancel, cancelContext, *result);
    if (status != RV_OK)
        return status;
    *output = result.release();
    return RV_OK;
#else
    UNUSED_PARAM(cancel);
    UNUSED_PARAM(cancelContext);
    return RV_ERR_UNSUPPORTED;
#endif
}

extern "C" void ranvier_print_pdf_data(RvPrintPdfData* value, const uint8_t** bytes, int64_t* length, int32_t* pageCount, int32_t* cancelled)
{
    *bytes = value->bytes.data();
    *length = value->bytes.size();
    *pageCount = value->pageCount;
    *cancelled = value->cancelled;
}

extern "C" void ranvier_print_pdf_release(RvPrintPdfData* value)
{
    delete value;
}
