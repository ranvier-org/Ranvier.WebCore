#include "config.h"
#include <WebCore/PlatformExportMacros.h>
#define MUTATION_TEST_EXPORT WEBCORE_EXPORT
#include "mutation_probe_contract.h"
#include "dom/RanvierDomGlue.h"
#include "ContextDestructionObserverInlines.h"
#include "Document.h"
#include "ExceptionOr.h"
#include "MutationCallback.h"
#include "MutationObserver.h"
#include "MutationRecord.h"
#include "Node.h"
#include "NodeList.h"
#include <memory>
#include <span>
#include <unordered_map>
#include <utility>
#include <vector>
#include <wtf/MainThread.h>
#include <wtf/NeverDestroyed.h>

namespace {
using namespace WebCore;
int callbackCount;
int contextCount;

struct Lease {
    TestMutationCallback callback;
    void* context;
    TestMutationRelease release;
    Lease(TestMutationCallback callback, void* context, TestMutationRelease release)
        : callback(callback), context(context), release(release) { ++contextCount; }
    ~Lease()
    {
        --contextCount;
        if (release)
            release(context);
    }
};

struct RecordStorage {
    TestMutationRecordView view { };
    std::vector<std::vector<uint16_t>> strings;
    std::vector<RvNode*> added;
    std::vector<RvNode*> removed;

    TestUtf16 text(const String& value)
    {
        if (value.isNull())
            return { nullptr, -1 };
        std::vector<uint16_t> units;
        units.reserve(value.length());
        for (unsigned i = 0; i < value.length(); ++i)
            units.push_back(value[i]);
        strings.push_back(std::move(units));
        auto& stored = strings.back();
        return { stored.data(), static_cast<int32_t>(stored.size()) };
    }

    explicit RecordStorage(MutationRecord& record)
    {
        strings.reserve(4);
        view.size = sizeof(view);
        view.type = text(record.type().string());
        view.target = reinterpret_cast<RvNode*>(&record.target());
        view.previous_sibling = reinterpret_cast<RvNode*>(record.previousSibling());
        view.next_sibling = reinterpret_cast<RvNode*>(record.nextSibling());
        view.attribute_name = text(record.attributeName().string());
        view.attribute_namespace = text(record.attributeNamespace().string());
        view.old_value = text(record.oldValue());
        for (unsigned i = 0; i < record.addedNodes().length(); ++i)
            added.push_back(reinterpret_cast<RvNode*>(record.addedNodes().item(i)));
        for (unsigned i = 0; i < record.removedNodes().length(); ++i)
            removed.push_back(reinterpret_cast<RvNode*>(record.removedNodes().item(i)));
        view.added_nodes = { added.data(), static_cast<int32_t>(added.size()) };
        view.removed_nodes = { removed.data(), static_cast<int32_t>(removed.size()) };
    }
};

struct Batch {
    MutationObserver::TakenRecords taken;
    std::vector<RecordStorage> records;
    explicit Batch(MutationObserver::TakenRecords&& value)
        : taken(WTF::move(value))
    {
        records.reserve(taken.records.size());
        for (auto& record : taken.records)
            records.emplace_back(record.get());
    }
};

struct BatchEntry {
    std::shared_ptr<Batch> batch;
    unsigned references { 1 };
};
auto& batches()
{
    static NeverDestroyed<std::unordered_map<TestMutationBatch*, BatchEntry>> value;
    return value.get();
}
TestMutationBatch* storeBatch(std::shared_ptr<Batch> value)
{
    auto* handle = reinterpret_cast<TestMutationBatch*>(value.get());
    batches().emplace(handle, BatchEntry { std::move(value), 1 });
    return handle;
}

struct State {
    WeakPtr<Document, WeakPtrImplWithEventTargetData> document;
    RefPtr<MutationObserver> observer;
    std::shared_ptr<Lease> lease;
    bool closed { false };
    State(Document& document, TestMutationCallback callback, void* context, TestMutationRelease release)
        : document(document), lease(std::make_shared<Lease>(callback, context, release)) { }
    void close()
    {
        if (std::exchange(closed, true))
            return;
        auto current = std::exchange(observer, nullptr);
        if (current)
            current->disconnect();
        lease.reset();
        document = nullptr;
    }
    bool active()
    {
        if (closed || !document || document->activeDOMObjectsAreStopped()) {
            close();
            return false;
        }
        return true;
    }
    ~State() { close(); }
};
auto& observers()
{
    static NeverDestroyed<std::unordered_map<TestMutationObserver*, std::shared_ptr<State>>> value;
    return value.get();
}
std::shared_ptr<State> lookup(TestMutationObserver* handle)
{
    auto found = observers().find(handle);
    return found == observers().end() ? nullptr : found->second;
}

class Callback final : public MutationCallback {
public:
    static Ref<MutationCallback> create(Document& document, std::weak_ptr<State> state)
    {
        return adoptRef(*new Callback(document, std::move(state)));
    }
    ~Callback() final { --callbackCount; }
    void contextDestroyed() final
    {
        Ref protect { *this };
        if (auto state = m_state.lock())
            state->close();
        ContextDestructionObserver::contextDestroyed();
    }
private:
    Callback(Document& document, std::weak_ptr<State> state)
        : MutationCallback(&document), m_state(std::move(state)) { ++callbackCount; }
    bool hasCallback() const final
    {
        auto state = m_state.lock();
        return state && !state->closed && state->lease;
    }
    CallbackResult<void> invoke(MutationObserver&, const Vector<Ref<MutationRecord>>& records, MutationObserver&) final
    {
        Ref protect { *this };
        auto state = m_state.lock();
        if (!state || !state->active() || !canInvokeCallback())
            return { };
        auto lease = state->lease;
        MutationObserver::TakenRecords snapshot { records, { } };
        for (auto& record : records)
            snapshot.pendingTargets.add(record->target());
        auto batch = std::make_shared<Batch>(WTF::move(snapshot));
        auto* handle = storeBatch(batch);
        lease->callback(lease->context, reinterpret_cast<TestMutationObserver*>(state.get()), handle);
        ranvier_test_mutation_batch_release(handle);
        return { };
    }
    CallbackResult<void> invokeRethrowingException(MutationObserver& observer, const Vector<Ref<MutationRecord>>& records, MutationObserver& owner) final
    {
        return invoke(observer, records, owner);
    }
    std::weak_ptr<State> m_state;
};

bool flag(int32_t value) { return value == 0 || value == 1; }
bool valid(TestOptionalBool value) { return flag(value.present) && flag(value.value); }
bool valid(TestUtf16 value) { return value.length >= 0 && (!value.length || value.data); }
std::optional<bool> option(TestOptionalBool value)
{
    return value.present ? std::optional<bool> { value.value != 0 } : std::nullopt;
}
}

int32_t ranvier_test_mutation_create(RvNode* handle, TestMutationCallback callback, void* context, TestMutationRelease release, TestMutationObserver** result)
{
    if (!result)
        return RV_ERR_NULL_ARGUMENT;
    *result = nullptr;
    if (!isMainThread())
        return RV_ERR_WRONG_THREAD;
    if (!handle || !callback)
        return RV_ERR_NULL_ARGUMENT;
    auto* document = dynamicDowncast<Document>(reinterpret_cast<Node*>(handle));
    if (!document)
        return RV_ERR_WRONG_INTERFACE;
    if (document->activeDOMObjectsAreStopped())
        return RV_ERR_DETACHED;
    auto state = std::make_shared<State>(*document, callback, context, release);
    state->observer = MutationObserver::create(Callback::create(*document, state));
    *result = reinterpret_cast<TestMutationObserver*>(state.get());
    observers().emplace(*result, std::move(state));
    return RV_OK;
}

int32_t ranvier_test_mutation_observe(TestMutationObserver* handle, RvNode* target, const TestMutationOptions* input)
{
    if (!isMainThread())
        return RV_ERR_WRONG_THREAD;
    auto state = lookup(handle);
    if (!state || !state->active())
        return RV_ERR_DETACHED;
    if (!target || !input || input->size != sizeof(*input) || !flag(input->child_list) || !flag(input->subtree)
        || !valid(input->attributes) || !valid(input->character_data) || !valid(input->attribute_old_value)
        || !valid(input->character_data_old_value) || !flag(input->attribute_filter.present)
        || input->attribute_filter.count < 0 || (input->attribute_filter.count && !input->attribute_filter.items))
        return RV_ERR_NULL_ARGUMENT;
    MutationObserver::Init options { };
    options.childList = input->child_list;
    options.subtree = input->subtree;
    options.attributes = option(input->attributes);
    options.characterData = option(input->character_data);
    options.attributeOldValue = option(input->attribute_old_value);
    options.characterDataOldValue = option(input->character_data_old_value);
    if (input->attribute_filter.present) {
        Vector<AtomString> filter;
        for (int32_t i = 0; i < input->attribute_filter.count; ++i) {
            auto item = input->attribute_filter.items[i];
            if (!valid(item))
                return RV_ERR_NULL_ARGUMENT;
            filter.append(AtomString { String { std::span<const char16_t> { reinterpret_cast<const char16_t*>(item.data), static_cast<size_t>(item.length) } } });
        }
        options.attributeFilter = WTF::move(filter);
    }
    auto result = state->observer->observe(*reinterpret_cast<Node*>(target), options);
    return result.hasException() ? Ranvier::recordException(result.releaseException()) : RV_OK;
}

int32_t ranvier_test_mutation_disconnect(TestMutationObserver* handle)
{
    if (!isMainThread()) return RV_ERR_WRONG_THREAD;
    auto state = lookup(handle);
    if (!state || !state->active()) return RV_ERR_DETACHED;
    state->observer->disconnect();
    return RV_OK;
}
int32_t ranvier_test_mutation_take_records(TestMutationObserver* handle, TestMutationBatch** result)
{
    if (!result) return RV_ERR_NULL_ARGUMENT;
    *result = nullptr;
    if (!isMainThread()) return RV_ERR_WRONG_THREAD;
    auto state = lookup(handle);
    if (!state || !state->active()) return RV_ERR_DETACHED;
    *result = storeBatch(std::make_shared<Batch>(state->observer->takeRecords()));
    return RV_OK;
}
int32_t ranvier_test_mutation_close(TestMutationObserver* handle)
{
    if (!isMainThread()) return RV_ERR_WRONG_THREAD;
    auto state = lookup(handle);
    if (!state) return RV_ERR_DETACHED;
    state->close();
    return RV_OK;
}
int32_t ranvier_test_mutation_release(TestMutationObserver* handle)
{
    if (!isMainThread()) return RV_ERR_WRONG_THREAD;
    auto state = lookup(handle);
    if (!state) return RV_ERR_DETACHED;
    observers().erase(handle);
    state->close();
    return RV_OK;
}
int32_t ranvier_test_mutation_batch_retain(TestMutationBatch* handle)
{
    if (!isMainThread()) return RV_ERR_WRONG_THREAD;
    auto found = batches().find(handle);
    if (found == batches().end()) return RV_ERR_DETACHED;
    ++found->second.references;
    return RV_OK;
}
int32_t ranvier_test_mutation_batch_release(TestMutationBatch* handle)
{
    if (!isMainThread()) return RV_ERR_WRONG_THREAD;
    auto found = batches().find(handle);
    if (found == batches().end()) return RV_ERR_DETACHED;
    if (!--found->second.references)
        batches().erase(found);
    return RV_OK;
}
int32_t ranvier_test_mutation_batch_count(TestMutationBatch* handle, int32_t* result)
{
    if (!result) return RV_ERR_NULL_ARGUMENT;
    *result = 0;
    if (!isMainThread()) return RV_ERR_WRONG_THREAD;
    auto found = batches().find(handle);
    if (found == batches().end()) return RV_ERR_DETACHED;
    *result = static_cast<int32_t>(found->second.batch->records.size());
    return RV_OK;
}
int32_t ranvier_test_mutation_batch_record(TestMutationBatch* handle, int32_t index, TestMutationRecordView* result)
{
    if (!result) return RV_ERR_NULL_ARGUMENT;
    auto size = result->size;
    *result = { };
    result->size = sizeof(*result);
    if (!isMainThread()) return RV_ERR_WRONG_THREAD;
    if (size != sizeof(*result)) return RV_ERR_NULL_ARGUMENT;
    auto found = batches().find(handle);
    if (found == batches().end()) return RV_ERR_DETACHED;
    if (index < 0 || static_cast<size_t>(index) >= found->second.batch->records.size()) return RV_ERR_NULL_ARGUMENT;
    *result = found->second.batch->records[index].view;
    return RV_OK;
}
int32_t ranvier_test_mutation_counts(TestMutationCounts* result)
{
    if (!result || result->size != sizeof(*result)) return RV_ERR_NULL_ARGUMENT;
    *result = { sizeof(*result), 0, 0, 0, 0 };
    if (!isMainThread()) return RV_ERR_WRONG_THREAD;
    result->observers = observers().size();
    result->callbacks = callbackCount;
    result->contexts = contextCount;
    result->batches = batches().size();
    return RV_OK;
}
