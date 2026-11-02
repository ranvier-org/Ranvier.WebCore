#include "config.h"
#include "print177_probe.h"
#include "CSSUnits.h"
#include "Document.h"
#include "DocumentView.h"
#include "FrameDestructionObserverInlines.h"
#include "GraphicsContextSkia.h"
#include "LocalFrame.h"
#include "LocalFrameView.h"
#include "Node.h"
#include "PrintContext.h"
#include "RenderingMode.h"
#include <WebCore/PlatformExportMacros.h>
#include <cmath>
#include <memory>
#include <vector>
#include <wtf/MainThread.h>
#include <include/core/SkCanvas.h>
#include <include/core/SkDocument.h>
#include <include/core/SkStream.h>
#include <include/docs/SkPDFDocument.h>
#include <include/docs/SkPDFJpegHelpers.h>

namespace {
using namespace WebCore;

struct Result {
    Print177Info info { sizeof(Print177Info), 3, 0, 0, 0, 0, 0, 0, 0 };
    std::vector<uint8_t> bytes;
};

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
        auto* first = static_cast<const uint8_t*>(data);
        if (count)
            m_bytes.insert(m_bytes.end(), first, first + count);
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
    ~PrintGuard() { end(); }
    PrintContext& context() { return m_context; }
    void begin(float width, float height)
    {
        m_begun = true;
        m_context->begin(width, height);
    }
    void end()
    {
        if (m_begun) {
            m_context->end();
            m_view->setScrollPosition(m_scroll);
            m_begun = false;
        }
    }

private:
    Ref<PrintContext> m_context;
    Ref<LocalFrameView> m_view;
    ScrollPosition m_scroll;
    bool m_begun { false };
};

bool valid(const Print177Options& options)
{
    if (options.size != sizeof(Print177Options) || options.no_event_pumping != 1 || options.reserved)
        return false;
    for (double value : { options.paper_width_points, options.paper_height_points,
             options.margin_top_points, options.margin_right_points,
             options.margin_bottom_points, options.margin_left_points }) {
        if (!std::isfinite(value) || value < 0 || value > 14400)
            return false;
    }
    return options.paper_width_points > options.margin_left_points + options.margin_right_points
        && options.paper_height_points > options.margin_top_points + options.margin_bottom_points
        && options.paper_width_points - options.margin_left_points - options.margin_right_points >= 1
        && options.paper_height_points - options.margin_top_points - options.margin_bottom_points >= 1
        && options.output_budget_bytes > 0 && options.output_budget_bytes <= 64 * 1024 * 1024
        && options.max_pages > 0 && options.max_pages <= 64 && options.cancel_after_pages >= -1
        && std::isfinite(options.raster_dpi) && options.raster_dpi >= 72 && options.raster_dpi <= 600;
}

void paint(Document& document, LocalFrame& frame, const Print177Options& options, Result& result)
{
    PrintGuard guard(frame);
    auto& context = guard.context();
    FloatBoxExtent margins(static_cast<float>(options.margin_top_points), static_cast<float>(options.margin_right_points),
        static_cast<float>(options.margin_bottom_points), static_cast<float>(options.margin_left_points));
    auto effectiveMargins = context.computedPageMargin(margins);
    FloatSize available(options.paper_width_points - margins.left() - margins.right(),
        options.paper_height_points - margins.top() - margins.bottom());
    auto pageSize = context.computedPageSize(available, margins);
    if (pageSize.isEmpty())
        return;
    auto layoutInputScale = static_cast<float>(CSS::pixelsPerPt / PrintContext::minimumShrinkFactor());
    guard.begin(pageSize.width() * layoutInputScale, pageSize.height() * layoutInputScale);
    if (document.frame() != &frame || !frame.view())
        return;
    float pageHeight = 0;
    context.computePageRects(FloatRect(FloatPoint(), pageSize), 0, 0, 1, pageHeight, false);
    result.info.page_count = context.pageCount();
    if (!context.pageCount() || context.pageCount() > options.max_pages)
        return;
    result.info.layout_page_width = context.pageRect(0).width();
    result.info.layout_page_height = context.pageRect(0).height();
    BoundedStream stream(options.output_budget_bytes);
    auto metadata = SkPDF::JPEG::MetadataWithCallbacks();
    metadata.fTitle = SkString("Print177 private renderer experiment");
    metadata.fRasterDPI = options.raster_dpi;
    auto pdf = SkPDF::MakeDocument(&stream, metadata);
    if (!pdf) {
        result.info.outcome = 2;
        return;
    }
    for (size_t index = 0; index < context.pageCount(); ++index) {
        if (options.cancel_after_pages >= 0 && result.info.painted_pages >= static_cast<uint32_t>(options.cancel_after_pages)) {
            result.info.outcome = 1;
            pdf->abort();
            return;
        }
        auto* canvas = pdf->beginPage(options.paper_width_points, options.paper_height_points);
        if (!canvas) {
            result.info.outcome = 2;
            pdf->abort();
            return;
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
        ++result.info.painted_pages;
        if (stream.failed()) {
            result.info.outcome = 2;
            pdf->abort();
            return;
        }
    }
    pdf->close();
    if (stream.failed()) {
        result.info.outcome = 2;
        return;
    }
    result.bytes = stream.take();
    result.info.pdf_bytes = result.bytes.size();
    result.info.outcome = result.bytes.empty() ? 2 : 0;
}
}

extern "C" WEBCORE_EXPORT int32_t ranvier_print177_export(void* documentHandle, const Print177Options* input, void** output)
{
    if (output)
        *output = nullptr;
    if (!output || !input || !documentHandle || !isMainThread())
        return -1;
    auto* documentPointer = dynamicDowncast<Document>(reinterpret_cast<Node*>(documentHandle));
    if (!documentPointer || !documentPointer->frame() || !documentPointer->frame()->view())
        return -1;
    Ref document = *documentPointer;
    Ref frame = *document->frame();
    auto result = std::make_unique<Result>();
    result->info.printing_before = document->printing();
    if (valid(*input) && !document->printing())
        paint(document, frame, *input, *result);
    result->info.printing_after = document->printing();
    *output = result.release();
    return 0;
}

extern "C" WEBCORE_EXPORT int32_t ranvier_print177_info(void* handle, Print177Info* output)
{
    if (!handle || !output || output->size != sizeof(Print177Info))
        return -1;
    *output = static_cast<Result*>(handle)->info;
    return 0;
}

extern "C" WEBCORE_EXPORT int32_t ranvier_print177_bytes(void* handle, const uint8_t** output, uint64_t* length)
{
    if (!handle || !output || !length)
        return -1;
    const auto& bytes = static_cast<Result*>(handle)->bytes;
    *output = bytes.empty() ? nullptr : bytes.data();
    *length = bytes.size();
    return 0;
}

extern "C" WEBCORE_EXPORT void ranvier_print177_release(void* handle)
{
    delete static_cast<Result*>(handle);
}
