import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('proof_layout', ROOT / 'scripts/collect_mac_recovery_proof.py')
layout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(layout)


class ProofLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.work = self.root / 'work'
        self.evidence = self.root / 'evidence'
        self.work.mkdir()
        self.evidence.mkdir()
        (self.evidence / 'recovery-receipt.json').write_text('{"productSource":"F"}')

    def test_one_root_retains_receipt_and_all_selected_payload_hashes(self):
        for relative in ['probe-logs/probe.log', 'mac-gpu-public-qualification/pixel.json', 'out/gpu/symbols/Host.dSYM/data']:
            path = self.work / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(relative)
        result = layout.collect(self.evidence, self.work, 'gpu')
        self.assertIn('recovery-receipt.json', result['members'])
        self.assertIn('product-gates/probe-logs/probe.log', result['members'])
        for name, expected in result['members'].items():
            self.assertEqual(hashlib.sha256((self.evidence / name).read_bytes()).hexdigest(), expected)
        self.assertEqual(json.loads((self.evidence / 'artifact-members.json').read_text()), result)

    def test_missing_optional_gate_outputs_do_not_invent_payloads(self):
        result = layout.collect(self.evidence, self.work, 'slim')
        self.assertEqual(set(result['members']), {'recovery-receipt.json'})
        self.assertTrue(all(not row['present'] for row in result['sources']))

    def test_nested_roots_and_bad_flavor_reject(self):
        for evidence, work, flavor in [(self.work / 'nested', self.work, 'slim'),
                                       (self.evidence, self.evidence / 'nested', 'slim'),
                                       (self.evidence, self.work, '../escape')]:
            with self.subTest(flavor=flavor), self.assertRaises(ValueError):
                layout.collect(evidence, work, flavor)

    def test_existing_seal_rejects_recollection(self):
        layout.collect(self.evidence, self.work, 'slim')
        with self.assertRaises(ValueError):
            layout.collect(self.evidence, self.work, 'slim')

    def test_workflow_uploads_only_the_owned_proof_root(self):
        text = (ROOT / '.github/workflows/macos-preview12-recovery.yml').read_text()
        final = text[text.index('      - name: Always retain original SDK and helper proof'):]
        self.assertIn('path: ${{ env.EVIDENCE }}', final)
        self.assertIn('include-hidden-files: true', final)
        self.assertNotIn('${{ env.RANVIER_WORK }}', final)
        self.assertLess(text.index('collect_mac_recovery_proof.py'), text.index('      - name: Always retain original SDK and helper proof'))


if __name__ == '__main__':
    unittest.main()
