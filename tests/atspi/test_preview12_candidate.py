"""P12 candidate source and exact qualification-run controls; no publication."""
import hashlib,importlib.util,json,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('preview12',ROOT/'scripts/prepare_atspi_preview12.py')
release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)


class Preview12CandidateTests(unittest.TestCase):
    def test_exact_two_rid_policy_and_unarmed_copy_stops_before_network(self):
        policy=json.loads((release.PROVIDER/'public-preview12.json').read_text())
        self.assertTrue(policy['armed']);release.aggregate.validate_policy(policy);self.assertEqual(policy['version'],'0.1.1-preview.12');self.assertEqual(policy['nativeVersion'],'0.1.1-preview.11')
        self.assertEqual(policy['providerSourceClaim'],'05adae5c9829472306e85b6b3b4aac068e79a5ec')
        self.assertEqual(policy['rids']['linux-x64']['proofKind'],'local-qualified-relayed');self.assertEqual(policy['rids']['linux-arm64']['proofKind'],'runner-executed')
        with tempfile.TemporaryDirectory() as d,patch.object(release.subprocess,'check_output') as network:
            with self.assertRaisesRegex(ValueError,'unarmed'):release.qualify_inputs(Path(d),dict(policy,armed=False))
            network.assert_not_called()

    def test_exact_run_path_head_event_and_outcome_are_required(self):
        for run,head,artifact,event,path in release.QUALIFICATIONS.values():
            good=dict(head_sha=head,event=event,path=path,conclusion='success')
            with patch.object(release.subprocess,'check_output',return_value=json.dumps(good)):release.check_run(run,head,event,path)
            for field,value in [('head_sha','0'*40),('event','pull_request'),('path','.github/workflows/wrong.yml'),('conclusion','failure')]:
                with self.subTest(field=field),patch.object(release.subprocess,'check_output',return_value=json.dumps(dict(good,**{field:value}))):
                    with self.assertRaises(ValueError):release.check_run(run,head,event,path)

    def test_exact_package_and_receipt_hashes_are_required(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'package').mkdir();package=root/'package/input.nupkg';package.write_bytes(b'package');receipt=root/'qualification-receipt.json';receipt.write_bytes(b'receipt')
            sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();pins=dict(packageSha256=sha(package),receiptSha256=sha(receipt))
            self.assertEqual(release.select_inputs(root,pins),(package,receipt))
            receipt.write_bytes(b'wrong')
            with self.assertRaises(ValueError):release.select_inputs(root,pins)

    def test_pending_publication_pins_reject_before_network(self):
        pins=json.loads((release.PROVIDER/'preview12-publication.json').read_text())
        release.validate_publication_pins(pins)
        with self.assertRaises(ValueError):release.validate_publication_pins(dict(pins,candidateRun=None))
        valid=dict(schemaVersion=1,id=release.IDENTITY,version=release.VERSION,candidateRun=1,candidateHead='a'*40,packageSha256='b'*64,candidateReceiptSha256='c'*64)
        release.validate_publication_pins(valid)
        for key,value in [('version','0.1.1-preview.11'),('candidateRun',True),('candidateHead','A'*40),('packageSha256',None)]:
            with self.subTest(key=key),self.assertRaises(ValueError):release.validate_publication_pins(dict(valid,**{key:value}))

    def test_absence_probe_is_p12_and_requires_404(self):
        with patch.object(release.urllib.request,'urlopen',side_effect=urllib.error.HTTPError('x',404,'absent',{},None)) as request:
            release.absent_public_version();self.assertIn('/0.1.1-preview.12/',request.call_args.args[0])
        with patch.object(release.urllib.request,'urlopen'),self.assertRaises(ValueError):release.absent_public_version()

    def test_candidate_workflow_is_manual_main_only_and_never_publishes(self):
        text=(ROOT/'.github/workflows/atspi-preview12-candidate.yml').read_text()
        self.assertIn("github.event_name == 'workflow_dispatch'",text);self.assertIn("github.ref == 'refs/heads/main'",text)
        self.assertIn('if: ${{ false &&',text)
        self.assertNotIn('id-token:',text.lower());self.assertNotIn('nuget push',text.lower());self.assertNotIn('cmake',text.lower())

    def test_publisher_is_main_manual_and_verifies_before_authentication(self):
        text=(ROOT/'.github/workflows/build.yml').read_text().split('  publish-atspi-preview12:',1)[1]
        self.assertNotIn("if: ${{ false &&",text)
        self.assertIn("inputs.atspi_preview11 == 'publish-p12'",text)
        self.assertIn("github.event_name == 'workflow_dispatch'",text)
        self.assertIn("github.ref == 'refs/heads/main'",text)
        self.assertLess(text.index('scripts/prepare_atspi_preview12.py verify'),text.index('NuGet/login@v1'))
        self.assertLess(text.index('NuGet/login@v1'),text.index('dotnet nuget push'))


if __name__=='__main__':unittest.main()
