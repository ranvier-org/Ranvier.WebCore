#pragma once

#include <stdint.h>

struct Print177Options {
    uint32_t size;
    uint32_t no_event_pumping;
    double paper_width_points;
    double paper_height_points;
    double margin_top_points;
    double margin_right_points;
    double margin_bottom_points;
    double margin_left_points;
    uint64_t output_budget_bytes;
    int32_t cancel_after_pages;
    uint32_t max_pages;
    float raster_dpi;
    uint32_t reserved;
};

struct Print177Info {
    uint32_t size;
    int32_t outcome;
    uint32_t page_count;
    uint32_t painted_pages;
    uint32_t printing_before;
    uint32_t printing_after;
    double layout_page_width;
    double layout_page_height;
    uint64_t pdf_bytes;
};
