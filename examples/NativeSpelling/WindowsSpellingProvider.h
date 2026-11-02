#pragma once

#include <windows.h>
#include <spellcheck.h>
#include <wrl/client.h>
#include <atomic>
#include <cstdint>
#include <cwchar>
#include <string>
#include <string_view>
#include <vector>

namespace RanvierNativeSpelling {

enum class State { Available, Unavailable, Cancelled, Failed };

struct Issue {
    uint32_t start { 0 };
    uint32_t length { 0 };
    CORRECTIVE_ACTION action { CORRECTIVE_ACTION_NONE };
    std::wstring replacement;
    std::vector<std::wstring> suggestions;
};

struct Result {
    State state { State::Failed };
    HRESULT error { E_UNEXPECTED };
    bool truncated { false };
    std::vector<Issue> issues;
};

namespace Detail {
struct Apartment {
    HRESULT status { CoInitializeEx(nullptr, COINIT_APARTMENTTHREADED) };
    ~Apartment() { if (SUCCEEDED(status)) CoUninitialize(); }
};

struct TaskString {
    LPWSTR value { nullptr };
    ~TaskString() { CoTaskMemFree(value); }
};

inline Result failed(HRESULT error) { return { State::Failed, error, false, { } }; }
inline Result cancelled() { return { State::Cancelled, HRESULT_FROM_WIN32(ERROR_CANCELLED), false, { } }; }

inline bool copyString(LPCWSTR source, std::wstring& result)
{
    if (!source) {
        result.clear();
        return true;
    }
    size_t count = 0;
    while (count <= 4096 && source[count])
        ++count;
    if (count > 4096)
        return false;
    result.assign(source, count);
    return true;
}
}

// Copies OS results; no engine handles enter the provider. Cancellation discards results after an OS call returns.
// The application checks request/document freshness and active composition before applying its chosen range edit.
inline Result checkWindowsSpelling(std::wstring_view language, std::wstring_view text, const std::atomic_bool* cancellation = nullptr)
{
    auto cancelled = [&] { return cancellation && cancellation->load(std::memory_order_relaxed); };
    if (cancelled())
        return Detail::cancelled();
    if (language.empty() || language.size() > 128 || language.find(L'\0') != language.npos
        || text.size() > 4096 || text.find(L'\0') != text.npos)
        return Detail::failed(E_INVALIDARG);
    Detail::Apartment apartment;
    if (FAILED(apartment.status) && apartment.status != RPC_E_CHANGED_MODE)
        return Detail::failed(apartment.status);
    Microsoft::WRL::ComPtr<ISpellCheckerFactory> factory;
    auto status = CoCreateInstance(__uuidof(SpellCheckerFactory), nullptr, CLSCTX_INPROC_SERVER, IID_PPV_ARGS(&factory));
    if (FAILED(status)) {
        if (status == REGDB_E_CLASSNOTREG)
            return { State::Unavailable, status, false, { } };
        return Detail::failed(status);
    }
    std::wstring tag(language);
    BOOL supported = FALSE;
    status = factory->IsSupported(tag.c_str(), &supported);
    if (FAILED(status))
        return Detail::failed(status);
    if (!supported)
        return { State::Unavailable, S_OK, false, { } };
    if (cancelled())
        return Detail::cancelled();
    Microsoft::WRL::ComPtr<ISpellChecker> checker;
    status = factory->CreateSpellChecker(tag.c_str(), &checker);
    if (FAILED(status))
        return Detail::failed(status);
    Result result { State::Available, S_OK, false, { } };
    if (text.empty())
        return result;
    std::wstring input(text);
    Microsoft::WRL::ComPtr<IEnumSpellingError> errors;
    status = checker->Check(input.c_str(), &errors);
    if (cancelled())
        return Detail::cancelled();
    if (FAILED(status) || !errors)
        return Detail::failed(FAILED(status) ? status : E_UNEXPECTED);
    for (;;) {
        Microsoft::WRL::ComPtr<ISpellingError> error;
        status = errors->Next(&error);
        if (cancelled())
            return Detail::cancelled();
        if (status == S_FALSE)
            break;
        if (FAILED(status) || !error)
            return Detail::failed(FAILED(status) ? status : E_UNEXPECTED);
        if (result.issues.size() == 64) {
            result.truncated = true;
            break;
        }
        Issue issue;
        ULONG start = 0, length = 0;
        if (FAILED(status = error->get_StartIndex(&start)) || FAILED(status = error->get_Length(&length))
            || FAILED(status = error->get_CorrectiveAction(&issue.action)))
            return Detail::failed(status);
        if (!length || start > input.size() || length > input.size() - start)
            return Detail::failed(E_UNEXPECTED);
        issue.start = start;
        issue.length = length;
        if (issue.action == CORRECTIVE_ACTION_REPLACE) {
            Detail::TaskString value;
            status = error->get_Replacement(&value.value);
            if (FAILED(status))
                return Detail::failed(status);
            if (!Detail::copyString(value.value, issue.replacement))
                return Detail::failed(HRESULT_FROM_WIN32(ERROR_BUFFER_OVERFLOW));
        }
        if (issue.action == CORRECTIVE_ACTION_GET_SUGGESTIONS) {
            auto word = input.substr(start, length);
            Microsoft::WRL::ComPtr<IEnumString> suggestions;
            status = checker->Suggest(word.c_str(), &suggestions);
            if (cancelled())
                return Detail::cancelled();
            if (FAILED(status) || !suggestions)
                return Detail::failed(FAILED(status) ? status : E_UNEXPECTED);
            for (;;) {
                Detail::TaskString value;
                ULONG fetched = 0;
                status = suggestions->Next(1, &value.value, &fetched);
                if (cancelled())
                    return Detail::cancelled();
                if (FAILED(status))
                    return Detail::failed(status);
                if (!fetched)
                    break;
                if (issue.suggestions.size() == 16) {
                    result.truncated = true;
                    break;
                }
                std::wstring suggestion;
                if (!Detail::copyString(value.value, suggestion))
                    return Detail::failed(HRESULT_FROM_WIN32(ERROR_BUFFER_OVERFLOW));
                issue.suggestions.push_back(std::move(suggestion));
            }
        }
        result.issues.push_back(std::move(issue));
    }
    return cancelled() ? Detail::cancelled() : result;
}

}
