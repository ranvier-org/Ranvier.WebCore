"""Relay metadata controls only; these never qualify a renderer or execute a compiler."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('preview11_relay', ROOT / 'scripts/relay_atspi_preview11_x64.py')
relay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay)


class RelayControls(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads(relay.POLICY.read_text())

    def test_unarmed_receiver_stops_before_network(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(relay.subprocess, 'check_output') as network:
            with self.assertRaisesRegex(ValueError, 'unarmed'):
                relay.receive(dict(self.policy, armed=False), Path(directory) / 'receive')
            network.assert_not_called()

    def test_transport_requires_every_exact_identity_pin(self):
        policy = dict(self.policy, armed=True, releaseId=1, assetId=2, assetName='proof.zip',
                      releaseAuthor='reviewed-owner', assetUploader='reviewed-owner')
        relay.validate_policy(policy, transport=True)
        for name in ['releaseId', 'assetId', 'assetBytes', 'assetName', 'releaseAuthor', 'assetUploader']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                relay.validate_policy(dict(policy, **{name:None}), transport=True)
        for name, value in [('proofKind','runner-executed'), ('testsExecutedByRelay',True), ('domVersion','0.1.0-alpha.56')]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                relay.validate_policy(dict(policy, **{name:value}))

    def test_receiver_rejects_non_main_non_dispatch_identity_before_network(self):
        for event, ref in [('push','refs/heads/main'), ('workflow_dispatch','refs/heads/other')]:
            with self.subTest(event=event, ref=ref), patch.dict(relay.os.environ,
                    dict(GITHUB_EVENT_NAME=event,GITHUB_REF=ref,GITHUB_SHA='a'*40)), patch.object(relay.subprocess,'check_output') as network:
                with self.assertRaisesRegex(ValueError,'receiver identity'):
                    relay.receive(self.policy,Path('not-created'))
                network.assert_not_called()

    def test_release_target_author_and_asset_metadata_are_bound(self):
        policy = dict(self.policy, releaseId=1, assetId=2, assetName='proof.zip',
                      releaseAuthor='owner', assetUploader='owner')
        release = dict(id=1, draft=True, target_commitish=policy['releaseTargetCommit'], author=dict(login='owner'),
                       assets=[dict(id=2, name='proof.zip', size=policy['assetBytes'], state='uploaded', uploader=dict(login='owner'), digest='sha256:' + policy['assetSha256'])])
        relay.validate_release(release, policy)
        for name, value in [('id',3), ('draft',False), ('target_commitish','main'), ('author',dict(login='other')), ('assets',[])]:
            with self.subTest(name=name), self.assertRaises(ValueError):
                relay.validate_release(dict(release, **{name:value}), policy)
        for name, value in [('id',3), ('name','other.zip'), ('size',1), ('state','new'), ('uploader',dict(login='other')), ('digest','sha256:'+'0'*64)]:
            bad = deepcopy(release)
            bad['assets'][0][name] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                relay.validate_release(bad, policy)

    def test_manifest_binds_all_members_and_rejects_unsafe_entries(self):
        def check(entries, manifest):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'evidence.zip'
                with zipfile.ZipFile(path, 'w') as zipped:
                    for name, data in entries:
                        zipped.writestr(name, data)
                    zipped.writestr(relay.MANIFEST, json.dumps(manifest))
                return relay.inventory(path)
        body = b'raw evidence'
        manifest = dict(files={'log.txt':relay.sha(body)})
        self.assertEqual(check([('log.txt',body)],manifest)[0], {'log.txt':body})
        for entries in [[('log.txt',b'changed')], [], [('log.txt',body),('extra',b'new')],
                        [('log.txt',body),('LOG.TXT',body)], [('../escape',body)], [('a\\b',body)], [('a:b',body)]]:
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                check(entries,manifest)
        link = zipfile.ZipInfo('link')
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaisesRegex(ValueError, 'regular files'):
            check([(link,b'target')],dict(files={'link':relay.sha(b'target')}))

    def test_bundle_outer_hash_precedes_member_loading(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'wrong.zip'
            path.write_bytes(b'not accepted evidence')
            with self.assertRaisesRegex(ValueError, 'bundle bytes'):
                relay.validate_bundle(path,self.policy)

    def test_receiver_is_main_dispatch_only_with_draft_read_access_and_no_publisher(self):
        text = (ROOT / '.github/workflows/build.yml').read_text()
        job = text.split('  relay-atspi-preview11-x64:',1)[1].split('  prepare-atspi-preview11:',1)[0]
        self.assertIn("github.event_name == 'workflow_dispatch'",job)
        self.assertIn("inputs.atspi_preview11 == 'relay-x64'",job)
        self.assertIn("github.ref == 'refs/heads/main'",job)
        self.assertIn('contents: write',job)
        self.assertIn('persist-credentials: false',job)
        for forbidden in ['dotnet', 'NuGet/login', 'id-token', 'cmake', 'ninja']:
            self.assertNotIn(forbidden,job)
        self.assertIn(relay.ARTIFACT,job)

    def test_receiver_requests_only_read_endpoints(self):
        text = (ROOT/'scripts/relay_atspi_preview11_x64.py').read_text()
        self.assertNotIn("'--method'",text)
        self.assertNotIn("'-X'",text)
        self.assertNotIn("'--field'",text)
        self.assertNotIn("'--raw-field'",text)
        self.assertIn("'repos/ranvier-org/Ranvier.WebCore/releases/'",text)
        self.assertIn("'repos/ranvier-org/Ranvier.WebCore/releases/assets/'",text)


if __name__ == '__main__':
    unittest.main()
