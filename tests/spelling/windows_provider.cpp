#include "../../examples/NativeSpelling/WindowsSpellingProvider.h"
#include <algorithm>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>

using namespace RanvierNativeSpelling;

static unsigned assertions;
static bool require(bool condition, const char* message)
{
    ++assertions;
    if (!condition)
        std::fprintf(stderr, "FAIL: %s\n", message);
    return condition;
}

static std::string quoted(std::wstring_view text)
{
    auto count = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text.data(), static_cast<int>(text.size()), nullptr, 0, nullptr, nullptr);
    std::string utf8(static_cast<size_t>(count), '\0');
    if (count)
        WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text.data(), static_cast<int>(text.size()), utf8.data(), count, nullptr, nullptr);
    std::string output = "\"";
    for (unsigned char ch : utf8) {
        if (ch == '\\' || ch == '"')
            output += '\\';
        if (ch < 0x20) {
            char escaped[7];
            std::snprintf(escaped, sizeof(escaped), "\\u%04x", ch);
            output += escaped;
        } else
            output += static_cast<char>(ch);
    }
    return output + '"';
}

int wmain(int argc, wchar_t** argv)
{
    if (argc != 2)
        return 64;
    std::atomic_bool cancelled { true };
    if (!require(checkWindowsSpelling(L"en-US", L"speling", &cancelled).state == State::Cancelled, "pre-cancelled request"))
        return 1;
    auto unsupported = checkWindowsSpelling(L"zz-ZZ", L"hello");
    if (!require(unsupported.state == State::Unavailable, "unknown installed language is explicitly unavailable"))
        return 1;
    if (!require(checkWindowsSpelling(L"", L"hello").state == State::Failed, "empty language fails"))
        return 1;
    auto correct = checkWindowsSpelling(L"en-US", L"hello world");
    if (correct.state == State::Unavailable) {
        std::ofstream(std::filesystem::path(argv[1])) << "{\"available\":false,\"language\":\"en-US\"}\n";
        std::puts("SPELLING_PROVIDER_UNAVAILABLE=en-US");
        return 77;
    }
    if (!require(correct.state == State::Available && correct.issues.empty(), "actual OS correct-word check"))
        return 1;
    if (!require(checkWindowsSpelling(L"en-US", L"").state == State::Available, "empty text is a successful empty check"))
        return 1;
    auto result = checkWindowsSpelling(L"en-US", L"\U0001F642 speling suffix");
    if (!require(result.state == State::Available && !result.truncated, "actual OS misspelling check"))
        return 1;
    auto issue = std::find_if(result.issues.begin(), result.issues.end(), [](const auto& value) { return value.start == 3 && value.length == 7; });
    if (!require(issue != result.issues.end(), "OS offsets count UTF-16 units after surrogate prefix"))
        return 1;
    if (!require(!issue->suggestions.empty(), "actual OS supplies a suggestion without fixed ordering"))
        return 1;
    if (!require(checkWindowsSpelling(L"en-US", std::wstring(4097, L'a')).state == State::Failed, "bounded request rejects overlong text"))
        return 1;
    std::wstring embedded { L'a', L'\0', L'b' };
    if (!require(checkWindowsSpelling(L"en-US", embedded).state == State::Failed, "embedded NUL is not silently truncated by LPCWSTR"))
        return 1;
    for (unsigned index = 0; index < 20; ++index) {
        auto repeated = checkWindowsSpelling(L"en-US", L"hello");
        if (!require(repeated.state == State::Available && repeated.issues.empty(), "repeated native provider ownership"))
            return 1;
    }
    std::ofstream output { std::filesystem::path(argv[1]) };
    output << "{\"available\":true,\"language\":\"en-US\",\"word\":\"speling\",\"start\":" << issue->start
           << ",\"length\":" << issue->length << ",\"suggestions\":[";
    bool first = true;
    for (auto& suggestion : issue->suggestions) {
        if (!first)
            output << ',';
        output << quoted(suggestion);
        first = false;
    }
    output << "],\"assertions\":" << assertions << "}\n";
    if (!output)
        return 1;
    std::printf("SPELLING_PROVIDER_ASSERTIONS=%u\n", assertions);
    return 0;
}
