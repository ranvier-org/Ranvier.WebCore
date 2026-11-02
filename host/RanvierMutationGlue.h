#pragma once
#include "RanvierWebCoreAbi.h"
#include <WebCore/PlatformExportMacros.h>

extern "C" {
WEBCORE_EXPORT int32_t ranvier_mutation_observer_create(RvNode* document, RvMutationCallback callback, void* context,
    RvMutationContextRelease release, RvMutationObserver** result);
WEBCORE_EXPORT int32_t ranvier_mutation_observer_observe(RvMutationObserver*, RvNode*, const RvMutationObserverOptions*);
WEBCORE_EXPORT int32_t ranvier_mutation_observer_disconnect(RvMutationObserver*);
WEBCORE_EXPORT int32_t ranvier_mutation_observer_take_records(RvMutationObserver*, RvMutationRecordBatch** result);
WEBCORE_EXPORT int32_t ranvier_mutation_observer_release(RvMutationObserver*);
WEBCORE_EXPORT int32_t ranvier_mutation_record_batch_retain(RvMutationRecordBatch*);
WEBCORE_EXPORT int32_t ranvier_mutation_record_batch_release(RvMutationRecordBatch*);
WEBCORE_EXPORT int32_t ranvier_mutation_record_batch_get_count(RvMutationRecordBatch*, int32_t* result);
WEBCORE_EXPORT int32_t ranvier_mutation_record_batch_get_record(RvMutationRecordBatch*, int32_t index, RvMutationRecordView* result);
WEBCORE_EXPORT void ranvier_mutation_observers_invalidate_document(RvNode* document);
}
