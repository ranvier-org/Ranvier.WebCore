/* Commit-charge and correctness harness for libpas on Windows.
 *   commit_test first     one small allocation must cost less than 8 MB of commit
 *   commit_test workload  commit must stay within the bytes in use plus 24 MB
 *   commit_test stress    allocate, write, verify, free and scavenge across every size class and four threads */
#include "bmalloc_heap.h"
#include "bmalloc_heap_inlines.h"
#include "pas_scavenger.h"
/* A WebKit build hides libpas's out-of-line entry points; bmalloc's C++ calls these inline ones. */
#define bmalloc_allocate bmalloc_allocate_inline
#define bmalloc_allocate_zeroed bmalloc_allocate_zeroed_inline
#define bmalloc_allocate_with_alignment bmalloc_allocate_with_alignment_inline
#define bmalloc_reallocate bmalloc_reallocate_inline
#define bmalloc_deallocate bmalloc_deallocate_inline
#include <windows.h>
#include <psapi.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#define MB (1024.0 * 1024.0)

/* bmalloc's C++ side defines these; the system heap stays off, as in a WebKit build without Malloc=1. */
#include "pas_system_heap.h"
#include <stdlib.h>
bool pas_system_heap_is_enabled(pas_heap_config_kind kind) { return false; }
bool pas_system_heap_should_supplant_bmalloc(pas_heap_config_kind kind) { return false; }
void* pas_system_heap_malloc(size_t size) { abort(); }
void* pas_system_heap_memalign(size_t alignment, size_t size) { abort(); }
void* pas_system_heap_realloc(void* ptr, size_t size) { abort(); }
void* pas_system_heap_malloc_compact(size_t size) { abort(); }
void* pas_system_heap_memalign_compact(size_t alignment, size_t size) { abort(); }
void* pas_system_heap_realloc_compact(void* ptr, size_t size) { abort(); }
void pas_system_heap_free(void* ptr) { abort(); }

static size_t private_commit(void)
{
    PROCESS_MEMORY_COUNTERS_EX counters;
    counters.cb = sizeof(counters);
    GetProcessMemoryInfo(GetCurrentProcess(), (PROCESS_MEMORY_COUNTERS*)&counters, sizeof(counters));
    return counters.PrivateUsage;
}

/* Private allocations of 1 MB or more: reserved and committed size of each. */
static void report_regions(void)
{
    MEMORY_BASIC_INFORMATION info;
    char* address = 0;
    void* base = 0;
    size_t reserved = 0, committed = 0;
    while (VirtualQuery(address, &info, sizeof(info))) {
        if (info.AllocationBase != base) {
            if (base && reserved >= (1 << 20))
                printf("  region %p reserved %8.2f MB committed %8.2f MB\n", base, reserved / MB, committed / MB);
            base = 0;
            reserved = committed = 0;
            if (info.State != MEM_FREE && info.Type == MEM_PRIVATE)
                base = info.AllocationBase;
        }
        if (base) {
            reserved += info.RegionSize;
            if (info.State == MEM_COMMIT)
                committed += info.RegionSize;
        }
        address = (char*)info.BaseAddress + info.RegionSize;
    }
}

static uint64_t next_random(uint64_t* state)
{
    *state ^= *state << 13;
    *state ^= *state >> 7;
    *state ^= *state << 17;
    return *state;
}

static int fail(const char* what, double value, double limit)
{
    printf("FAIL %s: %.2f MB, limit %.2f MB\n", what, value / MB, limit / MB);
    report_regions();
    return 1;
}

static int test_first(void)
{
    size_t before = private_commit();
    char* object = bmalloc_allocate(64, pas_non_compact_allocation_mode);
    memset(object, 7, 64);
    size_t grown = private_commit() - before;
    if (grown > 8 * MB)
        return fail("commit added by the first 64-byte allocation", grown, 8 * MB);
    printf("PASS first allocation added %.2f MB of commit\n", grown / MB);
    return 0;
}

static int test_workload(void)
{
    enum { count = 20000 };
    static char* objects[count];
    uint64_t seed = 88172645463325252ull;
    size_t before = private_commit(), in_use = 0;
    for (int i = 0; i < count; ++i) {
        size_t size = 16 + next_random(&seed) % 2033;
        pas_allocation_mode mode = i % 5 ? pas_non_compact_allocation_mode : pas_always_compact_allocation_mode;
        objects[i] = bmalloc_allocate(size, mode);
        memset(objects[i], i, size);
        in_use += size;
    }
    for (int i = 0; i < 6; ++i) {
        size_t size = (i < 3 ? 300 : 3000) * 1024;
        char* large = bmalloc_allocate(size, pas_non_compact_allocation_mode);
        memset(large, i, size);
        in_use += size;
    }
    size_t grown = private_commit() - before;
    printf("in use %.2f MB, commit added %.2f MB\n", in_use / MB, grown / MB);
    if (grown > in_use + 24 * MB)
        return fail("commit beyond the bytes in use", grown - in_use, 24 * MB);
    printf("PASS workload commit is within the bytes in use plus 24 MB\n");
    return 0;
}

static const size_t stress_sizes[] = { 1, 16, 24, 48, 100, 256, 500, 1000, 1616, 4000, 9000, 20000, 70000, 200000,
                                       500000, 1200000, 5000000 };
enum { stress_size_count = sizeof(stress_sizes) / sizeof(stress_sizes[0]), stress_slots = 1500 };

static DWORD WINAPI stress_thread(LPVOID argument)
{
    uint64_t seed = 0x9E3779B97F4A7C15ull * (1 + (uintptr_t)argument);
    char** objects = bmalloc_allocate_zeroed(stress_slots * sizeof(char*), pas_non_compact_allocation_mode);
    size_t* sizes = bmalloc_allocate_zeroed(stress_slots * sizeof(size_t), pas_non_compact_allocation_mode);
    size_t live = 0;
    for (int step = 0; step < 60000; ++step) {
        int slot = next_random(&seed) % stress_slots;
        if (objects[slot]) {
            unsigned char expected = (unsigned char)(slot * 31 + sizes[slot]);
            for (size_t i = 0; i < sizes[slot]; i += 97) {
                if ((unsigned char)objects[slot][i] != expected) {
                    printf("FAIL corrupted byte %zu of a %zu-byte object\n", i, sizes[slot]);
                    ExitProcess(2);
                }
            }
            live -= sizes[slot];
            if (next_random(&seed) % 4) {
                bmalloc_deallocate(objects[slot]);
                objects[slot] = 0;
                continue;
            }
            size_t grown_size = sizes[slot] * 2 + 1;
            objects[slot] = bmalloc_reallocate(objects[slot], grown_size, pas_non_compact_allocation_mode, pas_reallocate_free_if_successful);
            sizes[slot] = grown_size;
        } else {
            size_t size = stress_sizes[next_random(&seed) % stress_size_count];
            if (size > 100000 && live > 96 * 1024 * 1024)
                size = 256;
            sizes[slot] = size;
            switch (next_random(&seed) % 4) {
            case 0:
                objects[slot] = bmalloc_allocate(size, pas_always_compact_allocation_mode);
                break;
            case 1:
                objects[slot] = bmalloc_allocate_zeroed(size, pas_non_compact_allocation_mode);
                for (size_t i = 0; i < size; i += 61) {
                    if (objects[slot][i]) {
                        printf("FAIL zeroed allocation of %zu bytes is not zero at %zu\n", size, i);
                        ExitProcess(2);
                    }
                }
                break;
            case 2:
                objects[slot] = bmalloc_allocate_with_alignment(size, (size_t)1 << (4 + next_random(&seed) % 13), pas_non_compact_allocation_mode);
                break;
            default:
                objects[slot] = bmalloc_allocate(size, pas_non_compact_allocation_mode);
            }
        }
        memset(objects[slot], (unsigned char)(slot * 31 + sizes[slot]), sizes[slot]);
        live += sizes[slot];
        if (!(step % 15000))
            pas_scavenger_run_synchronously_now();
    }
    for (int slot = 0; slot < stress_slots; ++slot)
        bmalloc_deallocate(objects[slot]);
    bmalloc_deallocate(objects);
    bmalloc_deallocate(sizes);
    return 0;
}

static int test_stress(void)
{
    HANDLE threads[4];
    size_t before = private_commit();
    for (int round = 0; round < 2; ++round) {
        for (uintptr_t i = 0; i < 4; ++i)
            threads[i] = CreateThread(0, 0, stress_thread, (LPVOID)(i + 4 * round), 0, 0);
        WaitForMultipleObjects(4, threads, TRUE, INFINITE);
        for (int i = 0; i < 4; ++i) {
            DWORD code = 1;
            GetExitCodeThread(threads[i], &code);
            CloseHandle(threads[i]);
            if (code) {
                printf("FAIL a stress thread exited with %lu\n", code);
                return 1;
            }
        }
        size_t peak = private_commit() - before;
        pas_scavenger_run_synchronously_now();
        printf("round %d: commit %.2f MB before scavenging, %.2f MB after\n", round, peak / MB, (private_commit() - before) / MB);
    }
    printf("PASS stress\n");
    return 0;
}

int main(int argc, char** argv)
{
    const char* mode = argc > 1 ? argv[1] : "";
    int status = !strcmp(mode, "first") ? test_first() : !strcmp(mode, "workload") ? test_workload()
        : !strcmp(mode, "stress") ? test_stress() : (printf("usage: commit_test first|workload|stress\n"), 2);
    if (argc > 2 && !strcmp(argv[2], "regions"))
        report_regions();
    return status;
}
