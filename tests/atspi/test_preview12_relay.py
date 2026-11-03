"""Proof-only receiver policy and public graph fail-closed controls."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('relay12',ROOT/'scripts/relay_atspi_preview12_x64.py')
relay=importlib.util.module_from_spec(spec);spec.loader.exec_module(relay)


class Preview12RelayTests(unittest.TestCase):
    def setUp(self):
        self.policy=json.loads((ROOT/'providers/atspi/preview12-x64-relay.json').read_text())
        self.provider='Ranvier.Private.Accessibility.Atspi.X64Qualification';self.version='0.0.0-private12.1'
        self.libs={name+'/'+relay.managed.PUBLIC[name][0]:{'type':'package'} for name in relay.managed.selected('normal','linux-x64')}
        self.libs.update({'FSharp.Core/10.1.403':{'type':'package'},self.provider+'/'+self.version:{'type':'package'}})
        self.assets=dict(libraries=self.libs,targets={'net10.0/linux-x64':{'Ranvier.WebCore.Native.linux-x64/0.1.1-preview.11':{'native':{'libRanvierWebCoreHost.so':{}}}}})

    def test_unarmed_local_policy_is_valid_but_transport_rejected(self):
        relay.validate_policy(self.policy)
        with self.assertRaisesRegex(ValueError,'unarmed'):relay.validate_policy(self.policy,transport=True)

    def test_source_and_execution_claims_cannot_be_relabelled(self):
        for key,value in [('providerSourceClaim','0'*40),('nativeSourceClaim','0'*40),('viewSource','0'*40),('testsExecutedByRelay',True),('nativeVersion','0.1.1-preview.12')]:
            changed=deepcopy(self.policy);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):relay.validate_policy(changed)

    def test_transport_rejects_wrong_workflow_before_network(self):
        policy=deepcopy(self.policy);policy.update(armed=True,releaseId=1,assetId=2,releaseTargetCommit='a'*40,
                                                   assetName='proof.zip',releaseAuthor='owner',assetUploader='owner')
        env=dict(GITHUB_EVENT_NAME='workflow_dispatch',GITHUB_REF='refs/heads/main',GITHUB_SHA='b'*40,
                 GITHUB_WORKFLOW_REF='ranvier-org/Ranvier.WebCore/.github/workflows/wrong.yml@refs/heads/main')
        with patch.dict('os.environ',env,clear=True),patch.object(relay.subprocess,'check_output') as network:
            with self.assertRaisesRegex(ValueError,'workflow dispatch'):relay.receive(policy,Path('unused'))
            network.assert_not_called()

    def test_relay_workflow_remains_disabled_and_has_no_publish_or_engine_step(self):
        text=(ROOT/'.github/workflows/atspi-preview12-relay.yml').read_text()
        self.assertIn("false && github.event_name == 'workflow_dispatch'",text)
        self.assertIn("github.ref == 'refs/heads/main'",text)
        self.assertIn('persist-credentials: false',text)
        self.assertNotIn('nuget push',text.lower());self.assertNotIn('id-token:',text.lower());self.assertNotIn('cmake',text.lower())

    def test_exact_public_graph_accepts_resolved_other_rid_metadata(self):
        relay.validate_graph_shape(self.assets,'normal',self.provider,self.version)

    def test_project_mixed_mode_wrong_native_and_duplicate_provider_fail(self):
        for key,value in [('source/1',{'type':'project'}),('rAnViEr.ViEw.TrAcEd/9',{'type':'package'}),
                          ('Ranvier.WebCore.Native.Gpu.linux-x64/0.1.1-preview.11',{'type':'package'}),
                          (self.provider.lower()+'/0.0.0-private12.2',{'type':'package'})]:
            self.libs[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):relay.validate_graph_shape(self.assets,'normal',self.provider,self.version)
            del self.libs[key]
        self.assets['targets']['net10.0/linux-x64']['other/1']={'native':{'libRanvierWebCoreHost.so':{}}}
        with self.assertRaisesRegex(ValueError,'Host'):relay.validate_graph_shape(self.assets,'normal',self.provider,self.version)


if __name__=='__main__':unittest.main()
