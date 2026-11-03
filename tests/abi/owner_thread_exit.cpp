#include <windows.h>
#include <objbase.h>
#include <cstdio>
#include <cwchar>
#include <thread>
#include <initializer_list>

using Create = void* (*)(int, int);
using Destroy = void (*)(void*);

int wmain(int argc, wchar_t** argv)
{
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    if (argc != 3)
        return 2;
    auto module = LoadLibraryExW(argv[1], nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
    if (!module) {
        std::printf("LOAD_FAILED error=%lu\n", GetLastError());
        return 3;
    }
    auto create = reinterpret_cast<Create>(GetProcAddress(module, "rv_host_create"));
    auto destroy = reinterpret_cast<Destroy>(GetProcAddress(module, "rv_host_destroy"));
    if (!create || !destroy)
        return 4;
    bool valid = false;
    for (const wchar_t* mode : { L"main-none", L"worker-none", L"main-sta", L"worker-sta", L"main-mta", L"worker-mta" })
        valid |= std::wcscmp(argv[2], mode) == 0;
    if (!valid)
        return 2;
    bool worker = std::wcsncmp(argv[2], L"worker-", 7) == 0;
    bool sta = std::wcsstr(argv[2], L"-sta") != nullptr;
    bool mta = std::wcsstr(argv[2], L"-mta") != nullptr;
    int result = -1;
    std::printf("PROCESS_MAIN tid=%lu worker=%d sta=%d mta=%d\n", GetCurrentThreadId(), worker, sta, mta);
    auto run = [&] {
        HRESULT initialized = S_FALSE;
        if (sta || mta)
            initialized = CoInitializeEx(nullptr, sta ? COINIT_APARTMENTTHREADED : COINIT_MULTITHREADED);
        std::printf("OWNER_BEGIN tid=%lu com=%08lx\n", GetCurrentThreadId(), static_cast<unsigned long>(initialized));
        if (FAILED(initialized)) {
            result = 5;
            return;
        }
        void* host = create(80, 60);
        std::printf("AFTER_CREATE host=%p tid=%lu\n", host, GetCurrentThreadId());
        if (!host) {
            result = 6;
            if (sta || mta)
                CoUninitialize();
            return;
        }
        destroy(host);
        std::puts("AFTER_NATIVE_HOST_DESTROY");
        if (sta || mta)
            CoUninitialize();
        std::puts("AFTER_COM_UNINITIALIZE");
        result = 0;
        std::puts("OWNER_FUNCTION_RETURNING");
    };
    if (worker) {
        std::thread thread(run);
        thread.join();
        std::puts("OWNER_THREAD_JOINED");
    } else
        run();
    Sleep(250);
    std::printf("PROCESS_MAIN_RETURNING result=%d\n", result);
    return result;
}
