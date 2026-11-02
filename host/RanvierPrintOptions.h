#pragma once

#include "RanvierWebCoreAbi.h"
#include <cmath>
#include <initializer_list>

inline RvPrintOptions ranvierPrintDefaultOptions()
{
    return { sizeof(RvPrintOptions), 16, 612, 792, 36, 36, 36, 36, 8 * 1024 * 1024, 0, 0 };
}

inline bool ranvierPrintNormalizeOptions(RvPrintOptions& options, bool coreGraphics)
{
    if (options.size != sizeof(RvPrintOptions) || options.reserved || !options.max_pages || options.max_pages > 4096)
        return false;
    for (double value : { options.paper_width_points, options.paper_height_points,
             options.margin_top_points, options.margin_right_points,
             options.margin_bottom_points, options.margin_left_points }) {
        if (!std::isfinite(value) || value < 0 || value > 14400)
            return false;
    }
    if (!options.raster_dpi)
        options.raster_dpi = coreGraphics ? 72 : 144;
    return options.paper_width_points - options.margin_left_points - options.margin_right_points >= 1
        && options.paper_height_points - options.margin_top_points - options.margin_bottom_points >= 1
        && options.output_budget_bytes && options.output_budget_bytes <= 64 * 1024 * 1024
        && std::isfinite(options.raster_dpi) && options.raster_dpi >= 72 && options.raster_dpi <= 600
        && (!coreGraphics || options.raster_dpi == 72);
}
