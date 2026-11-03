import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('qualification_receipt', Path(__file__).with_name('qualification_receipt.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class QualificationReceipt(unittest.TestCase):
    def evidence(self):
        source, host, provider, package = 'a' * 40, 'b' * 64, 'c' * 64, 'd' * 64
        stage = dict(rid='linux-arm64', manifestDeclaredSource=source, unionExportGatePassed=True, nativeSha256=host)
        manifest = dict(rid='linux-arm64', abi=63, hostSha256=host, providerSha256=provider,
                        callerClaimedProviderSourceRevision=source, sourceProvenance='unverified-caller-claim')
        names = ['rv_test_' + str(index) for index in range(344)] + ['rv_host_ime_surrounding', 'rv_host_ime_delete_surrounding', 'rv_ax_text_style_run']
        style = [dict(passed=True) for _ in range(23)]
        report = dict(assertions=84, rows=[dict(passed=True) for _ in range(84)])
        process = dict(allOwnedProcessesExited=True, nativeBefore=host, nativeAfter=host, providerSha256=provider)
        protocols = {name: (report, process) for name in ('direct', 'queued', 'session')}
        sdk = dict(packageSha256=package, consumer=dict(loaded=True, providerSha256=provider))
        runs = []
        for mode in ('normal', 'traced'):
            for profile in ('present', 'absent', 'no-bus'):
                attached = profile == 'present'
                native = {'libRanvierWebCoreHost.so': host}
                if profile != 'absent':
                    native['libRanvierWebCoreAtspi.so'] = provider
                runs.append(dict(mode=mode, profile=profile, result=dict(windows=3, directHosts=3,
                    expectedAttached=attached, dynamicCodeSupported=False), nativeBefore=native,
                    nativeAfter=dict(native), nonBmpStyle=attached))
        managed = dict(rid='linux-arm64', hostSha256=host, providerSha256=provider, packageSha256=package,
                       sourceRevision=source, allOwnedProcessesExited=True, runs=runs)
        return [stage, manifest, package, source, '0.1.1-preview.8', names, set(names), style, protocols, sdk, managed]

    def test_complete_actual_evidence_produces_aggregate_shape(self):
        result = module.build_summary(*self.evidence())
        self.assertEqual(result['checks']['nativeExports'], 347)
        self.assertTrue(result['checks']['managedAot']['traced']['no-bus']['passed'])

    def test_missing_profile_cannot_be_promoted(self):
        evidence = self.evidence()
        evidence[-1]['runs'].pop()
        with self.assertRaises(ValueError):
            module.build_summary(*evidence)

    def test_x64_summary_requires_every_rid_to_match(self):
        evidence = self.evidence()
        for index in (0, 1, 10):
            evidence[index]['rid'] = 'linux-x64'
        self.assertEqual(module.build_summary(*evidence, rid='linux-x64')['rid'], 'linux-x64')
        for index in (0, 1, 10):
            evidence[index]['rid'] = 'linux-arm64'
            with self.assertRaises(ValueError):
                module.build_summary(*evidence, rid='linux-x64')
            evidence[index]['rid'] = 'linux-x64'
        with self.assertRaises(ValueError):
            module.build_summary(*evidence, rid='linux-riscv64')

    def test_changed_runtime_cannot_be_promoted(self):
        evidence = self.evidence()
        evidence[-1]['runs'][0]['nativeAfter']['libRanvierWebCoreHost.so'] = 'e' * 64
        with self.assertRaises(ValueError):
            module.build_summary(*evidence)

    def test_failed_protocol_cannot_be_promoted(self):
        evidence = self.evidence()
        evidence[8]['queued'][0]['rows'][0]['passed'] = False
        with self.assertRaises(ValueError):
            module.build_summary(*evidence)

    def test_wrong_source_claim_cannot_be_promoted(self):
        evidence = self.evidence()
        evidence[1]['callerClaimedProviderSourceRevision'] = 'e' * 40
        with self.assertRaises(ValueError):
            module.build_summary(*evidence)

    def test_wrong_abi_tail_cannot_be_promoted(self):
        evidence = self.evidence()
        evidence[5][-2:] = reversed(evidence[5][-2:])
        with self.assertRaises(ValueError):
            module.build_summary(*evidence)

    def test_failed_sdk_load_cannot_be_promoted(self):
        evidence = self.evidence()
        evidence[9]['consumer']['loaded'] = False
        with self.assertRaises(ValueError):
            module.build_summary(*evidence)


if __name__ == '__main__':
    unittest.main()
