import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'patches/0070-cocoa-texture-mapper-angle-dispatch.patch'
FIXTURE = ROOT / 'tests/fixtures/cocoa-angle-gl-dispatch.json'


class CocoaANGLEDispatch(unittest.TestCase):
    def setUp(self):
        self.patch = PATCH.read_text(encoding='utf-8')
        self.fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.mappings = dict(re.findall(r'^\+#define (gl\w+) (GL_\w+)$', self.patch, re.M))

    def test_every_captured_system_gl_import_has_an_angle_entry(self):
        self.assertEqual(len(self.fixture['systemOpenGLImports']), 62)
        for symbol in self.fixture['systemOpenGLImports']:
            name = symbol.removeprefix('_')
            self.assertEqual(self.mappings.get(name), 'GL_' + name[2:])

    def test_host_and_engine_source_calls_are_all_mapped(self):
        for relative in self.fixture['hostTranslationUnits']:
            source = (ROOT / 'host' / relative).read_text(encoding='utf-8')
            for name in set(re.findall(r'(?<![.>])\bgl[A-Z]\w*(?=\s*\()', source)):
                self.assertIn(name, self.mappings)
        for source, calls in self.fixture['sourceCallers'].items():
            self.assertTrue(set(calls) <= self.mappings.keys(), source)

    def test_mapping_does_not_rewrite_egl_or_gl_lookup_strings(self):
        self.assertEqual(set(self.mappings), set(self.fixture['mappedFunctions']))
        self.assertTrue(all(value == 'GL_' + key[2:] for key, value in self.mappings.items()))
        self.assertNotRegex(self.patch, r'^\+#define egl')
        self.assertNotIn('dlsym', self.patch)
        self.assertNotIn('dynamic_lookup', self.patch)

    def test_every_egl_consumer_is_explicit_and_spike_guarded(self):
        sections = self.patch.split('diff --git ')
        for name in ['GLContext.cpp', 'GLDisplay.cpp', 'GLFenceEGL.cpp', 'GLFenceGL.cpp']:
            section = next(part for part in sections if part and part.splitlines()[0].endswith('/' + name))
            self.assertRegex(section, r'\+#if defined\(RANVIER_MAC_GPU_SPIKE\) && RANVIER_MAC_GPU_SPIKE\n'
                             r'\+#include "TextureMapperANGLEDispatch.h"\n[ +]#endif')
        self.assertIn('+#elif USE(LIBEPOXY)', self.patch)
        self.assertIn('+        platform/graphics/texmap/TextureMapperANGLEDispatch.h', self.patch)


if __name__ == '__main__':
    unittest.main()
