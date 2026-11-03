#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

typedef void* Handle;
typedef unsigned int UInt;
typedef int Int;
typedef UInt (*MakeCurrent)(Handle, Handle, Handle, Handle);
typedef void* (*GetProc)(const char*);
typedef const unsigned char* (*GetString)(UInt);
typedef void (*GetInt)(UInt, Int*);
typedef void (*GetPrecision)(UInt, UInt, Int*, Int*);

UInt eglMakeCurrent(Handle display, Handle draw, Handle read, Handle context)
{
    static MakeCurrent original;
    static Handle reported;
    static void* library;
    if (!library) library = dlopen("libEGL.so.1", RTLD_LAZY | RTLD_NOLOAD);
    if (!original)
        original = (MakeCurrent)(library ? dlsym(library, "eglMakeCurrent") : dlsym(RTLD_NEXT, "eglMakeCurrent"));
    if (!original)
        return 0;
    UInt result = original(display, draw, read, context);
    if (!result || !context || context == reported)
        return result;
    reported = context;
    const char* path = getenv("RV_GL_PROFILE_PATH");
    GetProc getProc = (GetProc)(library ? dlsym(library, "eglGetProcAddress") : dlsym(RTLD_NEXT, "eglGetProcAddress"));
    if (!path || !getProc)
        return result;
    GetString getString = (GetString)getProc("glGetString");
    GetInt getInt = (GetInt)getProc("glGetIntegerv");
    GetPrecision getPrecision = (GetPrecision)getProc("glGetShaderPrecisionFormat");
    if (!getString || !getInt)
        return result;
    const unsigned char* version = getString(0x1F02);
    const unsigned char* renderer = getString(0x1F01);
    const unsigned char* vendor = getString(0x1F00);
    if (!version || !renderer || !vendor)
        return result;
    int major = 0, minor = 0;
    int isES = sscanf((const char*)version, "OpenGL ES %d.%d", &major, &minor) == 2;
    if (!isES) sscanf((const char*)version, "%d.%d", &major, &minor);
    int precisionSupported = getPrecision && ((isES && major >= 2) || major > 4 || (major == 4 && minor >= 1));
    FILE* file = fopen(path, "a");
    if (!file)
        return result;
    Int subpixel = 0;
    getInt(0x0D50, &subpixel);
    fprintf(file, "{\"pid\":%ld,\"context\":\"%p\",\"version\":\"%s\",\"renderer\":\"%s\",\"vendor\":\"%s\",\"subpixelBits\":%d,\"shaderPrecision\":[", (long)getpid(), context, version, renderer, vendor, subpixel);
    for (int shader = 0; precisionSupported && shader < 2; ++shader) {
        for (int precision = 0; precision < 3; ++precision) {
            Int range[2] = {0, 0}, bits = 0;
            getPrecision(shader ? 0x8B30 : 0x8B31, 0x8DF0 + precision, range, &bits);
            fprintf(file, "%s{\"shader\":\"%s\",\"kind\":\"%s\",\"range\":[%d,%d],\"bits\":%d}", shader || precision ? "," : "", shader ? "fragment" : "vertex", precision == 0 ? "low" : precision == 1 ? "medium" : "high", range[0], range[1], bits);
        }
    }
    fprintf(file, "]}\n");
    fclose(file);
    return result;
}

MakeCurrent epoxy_eglMakeCurrent = eglMakeCurrent;
