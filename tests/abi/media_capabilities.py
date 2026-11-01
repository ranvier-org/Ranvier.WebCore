"""B06 media capability queries against an actual runtime directory. Replays tests/fixtures/media-capabilities-cases.json
through rv_media_decoding_info and rv_media_encoding_info: each case the engine rejects returns RV_ERR_DOM_EXCEPTION with
"TypeError" and writes no operation, and each other case is SUCCEEDED on a later rv_run_loop_cycle, never inside the
starting call, with the answer of the media engine configuration providers that the "media-decoding-provider" and
"media-encoding-provider" facilities report: without one, unsupported, not smooth, not power efficient. Compares the
TypeError set with the Chromium oracle tests/fixtures/media-capabilities-oracle.json and requires every difference to
be a qualified one. Then the argument errors, rv_media_capabilities_info's outcome rules, rv_resource_cancel and
rv_resource_release before delivery, a new document and rv_host_destroy before delivery, and that no media facility
or setting changes."""

import argparse
import ctypes
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
OK, NULL_ARGUMENT, DOM_EXCEPTION, UNSUPPORTED = 0, -1, -3, -9
SUCCEEDED, CANCELLED, INVALIDATED = 0, 3, 4
FACILITY = 4
IMPLEMENTED, ENABLED, AVAILABLE = 1, 2, 4
DECODING = {'file': 0, 'media-source': 1, 'webrtc': 2}
ENCODING = {'record': 0, 'webrtc': 1}
HDR = {'smpteSt2086': 0, 'smpteSt2094-10': 1, 'smpteSt2094-40': 2}
GAMUT = {'srgb': 0, 'p3': 1, 'rec2020': 2}
TRANSFER = {'srgb': 0, 'pq': 1, 'hlg': 2}
WATCHED = ['video', 'web-audio', 'media-stream', 'media-recorder', 'web-codecs', 'encrypted-media', 'media-capabilities',
           'media-decoding-provider', 'media-encoding-provider']
GUARD = 200


class Video(ctypes.Structure):
    _fields_ = [('size', ctypes.c_int32), ('content_type', ctypes.c_void_p), ('content_type_length', ctypes.c_int32),
                ('width', ctypes.c_uint32), ('height', ctypes.c_uint32), ('bitrate', ctypes.c_uint64), ('framerate', ctypes.c_double),
                ('alpha_channel', ctypes.c_int32), ('hdr_metadata_type', ctypes.c_int32), ('color_gamut', ctypes.c_int32),
                ('transfer_function', ctypes.c_int32)]


class Audio(ctypes.Structure):
    _fields_ = [('size', ctypes.c_int32), ('content_type', ctypes.c_void_p), ('content_type_length', ctypes.c_int32),
                ('channels', ctypes.c_void_p), ('channels_length', ctypes.c_int32), ('bitrate', ctypes.c_int64),
                ('samplerate', ctypes.c_int64), ('spatial_rendering', ctypes.c_int32)]


Completion = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_int32, ctypes.c_int32, ctypes.c_int32)


def verify(native_directory):
    cases = json.loads((FIXTURES / 'media-capabilities-cases.json').read_text(encoding='utf-8'))
    oracle = json.loads((FIXTURES / 'media-capabilities-oracle.json').read_text(encoding='utf-8'))
    report = {'browser': oracle['browser'], 'decoding': [], 'encoding': [], 'differences': {}, 'providers': {}}
    keep = []

    def text(value):
        data = value.encode('utf-8')
        buffer = ctypes.create_string_buffer(data, len(data) or 1)
        keep.append(buffer)
        return ctypes.cast(buffer, ctypes.c_void_p), len(data)

    def video_of(case):
        pointer, length = text(case['video'])
        size = cases['video']
        return Video(ctypes.sizeof(Video), pointer, length, size['width'], size['height'], size['bitrate'],
                     case.get('framerate', size['framerate']), -1, HDR.get(case.get('hdrMetadataType'), -1),
                     GAMUT.get(case.get('colorGamut'), -1), TRANSFER.get(case.get('transferFunction'), -1))

    def audio_of(case):
        pointer, length = text(case['audio'])
        channels, channels_length = text(case['channels']) if 'channels' in case else (None, 0)
        spatial = case.get('spatialRendering')
        return Audio(ctypes.sizeof(Audio), pointer, length, channels, channels_length, case.get('audioBitrate', -1),
                     case.get('samplerate', -1), -1 if spatial is None else int(spatial))

    with SvgProbe(native_directory, 320, 240) as p:
        P, I, U64 = p.pointer, p.integer, ctypes.c_uint64
        expect = p.expect
        expect(p.bind('rv_abi_has', I, [ctypes.c_char_p])(b'media-capabilities') == 1, 'media-capabilities advertised')
        query_args = [P, I, ctypes.POINTER(Video), ctypes.POINTER(Audio), Completion, P, ctypes.POINTER(U64)]
        decoding = p.bind('rv_media_decoding_info', I, query_args)
        encoding = p.bind('rv_media_encoding_info', I, query_args)
        info = p.bind('rv_media_capabilities_info', I, [U64] + [ctypes.POINTER(I)] * 3)
        cancel = p.bind('rv_resource_cancel', I, [U64])
        release = p.bind('rv_resource_release', I, [U64])
        cycle = p.bind('rv_run_loop_cycle', I, [I])
        fact = p.bind('rv_host_capability_fact', I, [P, I, ctypes.c_char_p, I, ctypes.POINTER(I)])
        host_create = p.bind('rv_host_create', P, [I, I])
        host_destroy = p.bind('rv_host_destroy', None, [P])
        load_html_bytes = p.bind('rv_host_load_html', I, [P, ctypes.c_char_p, I])  # utf8 bytes and length (#145)
        load_html = lambda host, html: load_html_bytes(host, html, len(html))  # utf8 length
        p.load('<!doctype html><body>media', standalone=False)
        deliveries = {}

        def on_complete(context, outcome, width, height):
            deliveries.setdefault(context, []).append((outcome, width, height))

        completion = Completion(on_complete)

        def facts(host):
            result = {}
            for name in WATCHED:
                row = []
                for dimension in range(5):
                    value = I(99)
                    expect(fact(host, FACILITY, name.encode(), dimension, ctypes.byref(value)) == OK, name + ' fact')
                    row.append(value.value)
                result[name] = row
            return result

        before = facts(p.host)
        expect(before['media-capabilities'][IMPLEMENTED] == 1, 'media-capabilities implemented')
        providers = {}
        for name in ['media-decoding-provider', 'media-encoding-provider']:
            row = before[name]
            expect(row[IMPLEMENTED] in (0, 1) and row[AVAILABLE] == row[IMPLEMENTED], name + ' implemented equals available')
            providers[name] = row[IMPLEMENTED]
        report['providers'] = providers
        scripts = p.bind('rv_host_scripts_enabled', I, [P])(p.host)

        def drain(context):
            # A hang guard: the loop raises and counts nothing.
            for _ in range(GUARD):
                if context in deliveries:
                    return
                cycle(1)
            raise AssertionError('no delivery for context ' + str(context))

        def start(function, kind, case, context):
            video = video_of(case) if 'video' in case else None
            audio = audio_of(case) if 'audio' in case else None
            token = U64(0xdead)
            status = function(p.host, kind, ctypes.byref(video) if video else None, ctypes.byref(audio) if audio else None,
                              completion, context, ctypes.byref(token))
            return status, token

        context = 1
        for label, function, kinds, provider in [('decoding', decoding, DECODING, providers['media-decoding-provider']),
                                                 ('encoding', encoding, ENCODING, providers['media-encoding-provider'])]:
            browser = {row['name']: row for row in oracle[label]}
            differences = {}
            for case in cases[label]:
                context += 1
                status, token = start(function, kinds[case['type']], case, context)
                row = {'name': case['name']}
                if case['webkit'] == 'TypeError':
                    expect(status == DOM_EXCEPTION, case['name'] + ': status ' + str(status))
                    expect(p.text('rv_last_exception', [I], 0) == 'TypeError', case['name'] + ': TypeError')
                    expect(token.value == 0xdead, case['name'] + ': no operation written')
                    cycle(0)
                    expect(context not in deliveries, case['name'] + ': a rejected query is never delivered')
                    row['error'] = 'TypeError'
                else:
                    expect(status == OK, case['name'] + ': status ' + str(status))
                    expect(token.value not in (0, 0xdead), case['name'] + ': operation written')
                    expect(context not in deliveries, case['name'] + ': not delivered inside the starting call')
                    drain(context)
                    expect(deliveries[context] == [(SUCCEEDED, 0, 0)], case['name'] + ': one SUCCEEDED ' + str(deliveries[context]))
                    values = [I(7), I(7), I(7)]
                    expect(info(token, *map(ctypes.byref, values)) == OK, case['name'] + ': info')
                    answer = [v.value for v in values]
                    expect(all(v in (0, 1) for v in answer), case['name'] + ': boolean answer')
                    if not provider and case['type'] == 'webrtc' and sys.platform == 'darwin':
                        # macOS builds WebRTC in (config/mac.cmake), so MediaCapabilities answers webrtc queries
                        # from the engine's WebRTCProvider and libwebrtc's codec list, not from the host provider.
                        # VP8 is in that list; no capability override is registered, so smooth and powerEfficient
                        # stay false.
                        expect(answer == [1, 0, 0], case['name'] + ': answered by the engine WebRTC provider ' + str(answer))
                    elif not provider:
                        expect(answer == [0, 0, 0], case['name'] + ': unsupported without a provider ' + str(answer))
                    row.update(supported=answer[0], smooth=answer[1], powerEfficient=answer[2])
                    expect(release(token) == OK, case['name'] + ': release')
                    expect(info(token, *map(ctypes.byref, values)) == UNSUPPORTED, case['name'] + ': info after release')
                    cycle(0)
                    expect(len(deliveries[context]) == 1, case['name'] + ': nothing after release')
                chromium = browser[case['name']]
                if ('error' in chromium) != ('error' in row):
                    differences[case['name']] = {'webkit': row.get('error', 'resolve'), 'chromium': chromium.get('error', 'resolve')}
                report[label].append(row)
            expect(sorted(differences) == sorted(cases['qualified'][label]), label + ': differences are the qualified ones ' + str(sorted(differences)))
            report['differences'][label] = differences

        file_case = cases['decoding'][0]
        def valid_video():
            return video_of(file_case)

        def status_of(function, kind, video, audio, callback=completion, out=True):
            token = U64(0xdead)
            context_value = 900
            status = function(p.host, kind, ctypes.byref(video) if video else None, ctypes.byref(audio) if audio else None,
                              callback, context_value, ctypes.byref(token) if out else None)
            if status == OK:
                release(token)
            return status, token.value

        # Argument errors leave *operation untouched.
        expect(decoding(None, 0, ctypes.byref(valid_video()), None, completion, None, ctypes.byref(U64())) == NULL_ARGUMENT, 'null host')
        expect(status_of(decoding, 0, valid_video(), None, Completion())[0] == NULL_ARGUMENT, 'null completion')
        expect(status_of(decoding, 0, valid_video(), None, out=False)[0] == NULL_ARGUMENT, 'null operation')
        for label, function, kind in [('decoding type 3', decoding, 3), ('decoding type -1', decoding, -1), ('encoding type 2', encoding, 2)]:
            expect(status_of(function, kind, valid_video(), None) == (UNSUPPORTED, 0xdead), label)
        broken = []
        for field, value in [('size', ctypes.sizeof(Video) - 8), ('alpha_channel', 2), ('hdr_metadata_type', 3), ('color_gamut', -2),
                             ('transfer_function', 3), ('content_type_length', -1)]:
            video = valid_video()
            setattr(video, field, value)
            broken.append(('video ' + field, video, None))
        bad = ctypes.create_string_buffer(b'video/webm;codecs="\xff"')
        keep.append(bad)
        video = valid_video()
        video.content_type, video.content_type_length = ctypes.cast(bad, ctypes.c_void_p), len(bad.value)
        broken.append(('video non-UTF-8 content type', video, None))
        video = valid_video()
        video.content_type, video.content_type_length = None, 3
        broken.append(('video NULL content type with a length', video, None))
        audio_case = next(case for case in cases['decoding'] if case['name'] == 'audio full')
        for field, value in [('size', 0), ('spatial_rendering', 2), ('samplerate', 1 << 32), ('channels', None)]:
            audio = audio_of(audio_case)
            setattr(audio, field, value)
            broken.append(('audio ' + field, None, audio))
        for label, video, audio in broken:
            expect(status_of(decoding, 0, video, audio) == (UNSUPPORTED, 0xdead), label)
        # The edges of the ranges are accepted.
        audio = audio_of(audio_case)
        audio.samplerate = (1 << 32) - 1
        expect(status_of(decoding, 0, None, audio)[0] == OK, 'samplerate UINT32_MAX')
        video = valid_video()
        video.content_type, video.content_type_length = None, 0
        expect(status_of(decoding, 0, video, None)[0] == DOM_EXCEPTION, 'NULL empty content type is the engine TypeError')
        video = valid_video()
        video.alpha_channel = 1
        expect(status_of(decoding, 0, video, None)[0] == OK, 'alpha channel present')

        # Info outcome rules.
        values = [I(7), I(7), I(7)]
        expect(info(0, *map(ctypes.byref, values)) == UNSUPPORTED, 'info of an unknown token')
        expect(info(1, None, ctypes.byref(values[1]), ctypes.byref(values[2])) == NULL_ARGUMENT, 'info NULL output')

        def pending(function=decoding, host=None, context_value=0):
            token = U64()
            expect(function(host or p.host, 0, ctypes.byref(valid_video()), None, completion, context_value, ctypes.byref(token)) == OK,
                   'pending query')
            expect(context_value not in deliveries, 'pending query not delivered inside the call')
            return token

        # Without a provider the answer is reached inside the starting call and delivered later. Cancel, release, a new
        # document and rv_host_destroy keep a reached answer; with a provider the outcome ends CANCELLED or INVALIDATED
        # when the provider has not answered yet.
        def reached(inside, fallback):
            return [(SUCCEEDED, 0, 0)] if inside else None

        def settled(context_value, expected, fallback, label):
            outcome = deliveries.get(context_value)
            if expected is None:
                expect(outcome in ([(SUCCEEDED, 0, 0)], [(fallback, 0, 0)]), label + ' ' + str(outcome))
            else:
                expect(outcome == expected, label + ' ' + str(outcome))

        # True when the decoding or encoding answer is reached inside the starting call.
        decoding_inside = not providers['media-decoding-provider']
        encoding_inside = not providers['media-encoding-provider']
        if sys.platform == 'darwin':
            # The Cocoa decoding provider calls back inside createDecodingConfiguration
            # (createMediaPlayerDecodingConfigurationCocoa, PlatformMediaEngineConfigurationFactoryCocoa.cpp), so the
            # file query answer is reached inside the starting call.
            decoding_inside = True
        token = pending(context_value=1001)
        expect(cancel(token) == OK, 'cancel')
        settled(1001, reached(decoding_inside, CANCELLED), CANCELLED, 'cancel delivers the reached answer before it returns')
        cycle(1)
        expect(release(token) == OK and release(token) == OK and len(deliveries[1001]) == 1, 'one delivery after cancel')
        token = pending(encoding, context_value=1002)
        expect(release(token) == OK, 'release')
        settled(1002, reached(encoding_inside, CANCELLED), CANCELLED, 'release delivers the reached answer before it returns')
        expect(info(token, *map(ctypes.byref, values)) == UNSUPPORTED and [v.value for v in values] == [7, 7, 7], 'info after release')
        cycle(1)
        expect(len(deliveries[1002]) == 1, 'nothing after release')
        # A delivered answer survives cancel until release.
        token = pending(context_value=1003)
        drain(1003)
        expect(cancel(token) == OK and deliveries[1003] == [(SUCCEEDED, 0, 0)], 'cancel after delivery delivers nothing')
        expect(info(token, *map(ctypes.byref, values)) == OK, 'info after a late cancel')
        release(token)
        # A new document before delivery.
        token = pending(context_value=1004)
        expect(load_html(p.host, b'<!doctype html><body>next') == OK, 'new document')
        if decoding_inside:
            expect(1004 not in deliveries, 'a reached answer is not delivered inside rv_host_load_html')
            drain(1004)
        settled(1004, reached(decoding_inside, INVALIDATED), INVALIDATED, 'new document keeps the reached answer')
        expect((info(token, *map(ctypes.byref, values)) == OK) == (deliveries[1004][0][0] == SUCCEEDED), 'info follows the outcome')
        expect(release(token) == OK and len(deliveries[1004]) == 1, 'one delivery after a new document')
        # A delivered answer survives a new document until release.
        token = pending(context_value=1005)
        drain(1005)
        load_html(p.host, b'<!doctype html><body>again')
        expect(info(token, *map(ctypes.byref, values)) == OK and deliveries[1005] == [(SUCCEEDED, 0, 0)], 'delivered answer kept')
        release(token)
        # rv_host_destroy before delivery; the token stays releasable.
        second = host_create(64, 64)
        expect(bool(second), 'second host')
        expect(load_html(second, b'<!doctype html><body>second') == OK, 'second document')
        token = pending(host=second, context_value=1006)
        host_destroy(second)
        if decoding_inside:
            expect(1006 not in deliveries, 'a reached answer is not delivered inside rv_host_destroy')
            drain(1006)
        settled(1006, reached(decoding_inside, INVALIDATED), INVALIDATED, 'host destroy keeps the reached answer')
        expect(release(token) == OK and len(deliveries[1006]) == 1, 'one delivery after host destroy')

        # No query changes a media facility or the script setting.
        expect(facts(p.host) == before, 'media facilities unchanged')
        expect(p.bind('rv_host_scripts_enabled', I, [P])(p.host) == scripts == 0, 'scripts stay disabled')
        report['assertions'] = p.assertions
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--report')
    args = parser.parse_args()
    report = verify(args.native_directory)
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=1), encoding='utf-8')
    print('PASS media_capabilities: ' + str(report['assertions']) + ' assertions; providers ' + json.dumps(report['providers'])
          + '; qualified differences ' + str(sum(len(v) for v in report['differences'].values())), flush=True)


if __name__ == '__main__':
    main()
