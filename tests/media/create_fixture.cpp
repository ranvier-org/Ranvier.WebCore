#include <windows.h>
#include <mfapi.h>
#include <mfidl.h>
#include <mfreadwrite.h>
#include <wrl/client.h>
#include <cmath>
#include <cstdio>

using Microsoft::WRL::ComPtr;

static HRESULT writeFixture(const wchar_t* destination)
{
    ComPtr<IMFSinkWriter> writer;
    auto status = MFCreateSinkWriterFromURL(destination, nullptr, nullptr, &writer);
    if (FAILED(status))
        return status;
    ComPtr<IMFMediaType> video;
    if (FAILED(status = MFCreateMediaType(&video))
        || FAILED(status = video->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Video))
        || FAILED(status = video->SetGUID(MF_MT_SUBTYPE, MFVideoFormat_H264))
        || FAILED(status = video->SetUINT32(MF_MT_AVG_BITRATE, 400000))
        || FAILED(status = video->SetUINT32(MF_MT_INTERLACE_MODE, MFVideoInterlace_Progressive))
        || FAILED(status = MFSetAttributeSize(video.Get(), MF_MT_FRAME_SIZE, 96, 64))
        || FAILED(status = MFSetAttributeRatio(video.Get(), MF_MT_FRAME_RATE, 30, 1))
        || FAILED(status = MFSetAttributeRatio(video.Get(), MF_MT_PIXEL_ASPECT_RATIO, 1, 1)))
        return status;
    DWORD videoIndex = 0;
    ComPtr<IMFMediaType> videoInput;
    if (FAILED(status = writer->AddStream(video.Get(), &videoIndex))
        || FAILED(status = MFCreateMediaType(&videoInput))
        || FAILED(status = video->CopyAllItems(videoInput.Get()))
        || FAILED(status = videoInput->SetGUID(MF_MT_SUBTYPE, MFVideoFormat_RGB32))
        || FAILED(status = writer->SetInputMediaType(videoIndex, videoInput.Get(), nullptr)))
        return status;
    ComPtr<IMFMediaType> audio;
    if (FAILED(status = MFCreateMediaType(&audio))
        || FAILED(status = audio->SetGUID(MF_MT_MAJOR_TYPE, MFMediaType_Audio))
        || FAILED(status = audio->SetGUID(MF_MT_SUBTYPE, MFAudioFormat_AAC))
        || FAILED(status = audio->SetUINT32(MF_MT_AUDIO_NUM_CHANNELS, 1))
        || FAILED(status = audio->SetUINT32(MF_MT_AUDIO_SAMPLES_PER_SECOND, 48000))
        || FAILED(status = audio->SetUINT32(MF_MT_AUDIO_BITS_PER_SAMPLE, 16))
        || FAILED(status = audio->SetUINT32(MF_MT_AUDIO_AVG_BYTES_PER_SECOND, 12000))
        || FAILED(status = audio->SetUINT32(MF_MT_AUDIO_BLOCK_ALIGNMENT, 1)))
        return status;
    DWORD audioIndex = 0;
    ComPtr<IMFMediaType> audioInput;
    if (FAILED(status = writer->AddStream(audio.Get(), &audioIndex))
        || FAILED(status = MFCreateMediaType(&audioInput))
        || FAILED(status = audio->CopyAllItems(audioInput.Get()))
        || FAILED(status = audioInput->SetGUID(MF_MT_SUBTYPE, MFAudioFormat_PCM))
        || FAILED(status = audioInput->SetUINT32(MF_MT_AUDIO_AVG_BYTES_PER_SECOND, 96000))
        || FAILED(status = audioInput->SetUINT32(MF_MT_AUDIO_BLOCK_ALIGNMENT, 2))
        || FAILED(status = writer->SetInputMediaType(audioIndex, audioInput.Get(), nullptr))
        || FAILED(status = writer->BeginWriting()))
        return status;
    std::puts("MEDIA_FIXTURE_BEGIN_WRITING");
    for (unsigned frame = 0; frame < 60; ++frame) {
        LONGLONG start = static_cast<LONGLONG>(frame) * 10000000 / 30;
        LONGLONG end = static_cast<LONGLONG>(frame + 1) * 10000000 / 30;
        ComPtr<IMFSample> videoSample;
        ComPtr<IMFMediaBuffer> videoBuffer;
        if (FAILED(status = MFCreateSample(&videoSample))
            || FAILED(status = MFCreateMemoryBuffer(96 * 64 * 4, &videoBuffer)))
            return status;
        BYTE* pixels = nullptr;
        if (FAILED(status = videoBuffer->Lock(&pixels, nullptr, nullptr)))
            return status;
        unsigned phase = frame / 20;
        for (unsigned index = 0; index < 96 * 64; ++index) {
            pixels[index * 4] = phase == 2 ? 255 : 0;
            pixels[index * 4 + 1] = phase == 1 ? 255 : 0;
            pixels[index * 4 + 2] = phase == 0 ? 255 : 0;
            pixels[index * 4 + 3] = 255;
        }
        videoBuffer->Unlock();
        if (FAILED(status = videoBuffer->SetCurrentLength(96 * 64 * 4))
            || FAILED(status = videoSample->AddBuffer(videoBuffer.Get()))
            || FAILED(status = videoSample->SetSampleTime(start))
            || FAILED(status = videoSample->SetSampleDuration(end - start))
            || FAILED(status = writer->WriteSample(videoIndex, videoSample.Get())))
            return status;
        ComPtr<IMFSample> audioSample;
        ComPtr<IMFMediaBuffer> audioBuffer;
        if (FAILED(status = MFCreateSample(&audioSample))
            || FAILED(status = MFCreateMemoryBuffer(1600 * 2, &audioBuffer)))
            return status;
        BYTE* audioData = nullptr;
        if (FAILED(status = audioBuffer->Lock(&audioData, nullptr, nullptr)))
            return status;
        for (unsigned sample = 0; sample < 1600; ++sample) {
            auto value = static_cast<short>(1200 * std::sin(2 * 3.14159265358979323846 * 440 * (frame * 1600 + sample) / 48000));
            audioData[sample * 2] = static_cast<BYTE>(static_cast<unsigned short>(value) & 255);
            audioData[sample * 2 + 1] = static_cast<BYTE>(static_cast<unsigned short>(value) >> 8);
        }
        audioBuffer->Unlock();
        if (FAILED(status = audioBuffer->SetCurrentLength(1600 * 2))
            || FAILED(status = audioSample->AddBuffer(audioBuffer.Get()))
            || FAILED(status = audioSample->SetSampleTime(start))
            || FAILED(status = audioSample->SetSampleDuration(end - start))
            || FAILED(status = writer->WriteSample(audioIndex, audioSample.Get())))
            return status;
    }
    std::puts("MEDIA_FIXTURE_FINALIZE");
    return writer->Finalize();
}

int wmain(int argc, wchar_t** argv)
{
    if (argc != 2)
        return 64;
    auto com = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    if (FAILED(com))
        return 1;
    auto startup = MFStartup(MF_VERSION);
    auto status = FAILED(startup) ? startup : writeFixture(argv[1]);
    if (SUCCEEDED(startup))
        MFShutdown();
    CoUninitialize();
    std::printf("MEDIA_FIXTURE_HRESULT=%08lx\n", static_cast<unsigned long>(status));
    return FAILED(status) ? 1 : 0;
}
