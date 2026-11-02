#pragma once
#include "../../host/RanvierWebCoreAbi.h"

#ifndef MUTATION_TEST_EXPORT
#define MUTATION_TEST_EXPORT
#endif

typedef struct TestMutationObserver TestMutationObserver;
typedef struct TestMutationBatch TestMutationBatch;
typedef struct { int32_t present; int32_t value; } TestOptionalBool;
typedef struct { const uint16_t* data; int32_t length; } TestUtf16;
typedef struct { int32_t present; const TestUtf16* items; int32_t count; } TestOptionalStrings;
typedef struct { RvNode* const* items; int32_t count; } TestNodes;

typedef struct TestMutationOptions {
    uint32_t size;
    int32_t child_list;
    int32_t subtree;
    TestOptionalBool attributes;
    TestOptionalBool character_data;
    TestOptionalBool attribute_old_value;
    TestOptionalBool character_data_old_value;
    TestOptionalStrings attribute_filter;
} TestMutationOptions;

typedef struct TestMutationRecordView {
    uint32_t size;
    TestUtf16 type;
    RvNode* target;
    TestNodes added_nodes;
    TestNodes removed_nodes;
    RvNode* previous_sibling;
    RvNode* next_sibling;
    TestUtf16 attribute_name;
    TestUtf16 attribute_namespace;
    TestUtf16 old_value;
} TestMutationRecordView;

typedef struct TestMutationCounts {
    uint32_t size;
    int32_t observers;
    int32_t callbacks;
    int32_t contexts;
    int32_t batches;
} TestMutationCounts;

typedef void (*TestMutationCallback)(void*, TestMutationObserver*, TestMutationBatch*);
typedef void (*TestMutationRelease)(void*);

#ifdef __cplusplus
extern "C" {
#endif
MUTATION_TEST_EXPORT int32_t ranvier_test_mutation_create(RvNode*, TestMutationCallback, void*, TestMutationRelease, TestMutationObserver**);
MUTATION_TEST_EXPORT int32_t ranvier_test_mutation_observe(TestMutationObserver*, RvNode*, const TestMutationOptions*);
MUTATION_TEST_EXPORT int32_t ranvier_test_mutation_disconnect(TestMutationObserver*);
MUTATION_TEST_EXPORT int32_t ranvier_test_mutation_take_records(TestMutationObserver*, TestMutationBatch**);
MUTATION_TEST_EXPORT int32_t ranvier_test_mutation_close(TestMutationObserver*);
MUTATION_TEST_EXPORT int32_t ranvier_test_mutation_release(TestMutationObserver*);
MUTATION_TEST_EXPORT int32_t ranvier_test_mutation_batch_retain(TestMutationBatch*);
MUTATION_TEST_EXPORT int32_t ranvier_test_mutation_batch_release(TestMutationBatch*);
MUTATION_TEST_EXPORT int32_t ranvier_test_mutation_batch_count(TestMutationBatch*, int32_t*);
MUTATION_TEST_EXPORT int32_t ranvier_test_mutation_batch_record(TestMutationBatch*, int32_t, TestMutationRecordView*);
MUTATION_TEST_EXPORT int32_t ranvier_test_mutation_counts(TestMutationCounts*);
#ifdef __cplusplus
}
#endif
