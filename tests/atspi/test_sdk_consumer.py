"""Manifest and selected-output controls; fixtures never load a native library."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('sdk_consumer',Path(__file__).with_name('consumer.py'))
consumer=importlib.util.module_from_spec(spec);spec.loader.exec_module(consumer)


def aggregate():
    return dict(schemaVersion=2,abi=63,hostBundled=False,runtimes={rid:dict(rid=rid,abi=63,hostSha256=host*64,providerSha256=provider*64) for rid,host,provider in [('linux-x64','a','b'),('linux-arm64','c','d')]})


class SdkConsumerTests(unittest.TestCase):
    def test_legacy_default_and_explicit_matching_rid_are_preserved(self):
        value=dict(abi=63,hostBundled=False,rid='linux-x64',hostSha256='a'*64,providerSha256='b'*64)
        self.assertEqual(consumer.select_runtime(value,None),value)
        self.assertEqual(consumer.select_runtime(value,'linux-x64'),value)
        with self.assertRaises(ValueError):consumer.select_runtime(value,'linux-arm64')

    def test_aggregate_requires_explicit_existing_rid(self):
        value=aggregate()
        for rid in ['linux-x64','linux-arm64']:
            self.assertEqual(consumer.select_runtime(value,rid),value['runtimes'][rid])
        for rid in [None,'win-x64','linux-unknown']:
            with self.subTest(rid=rid),self.assertRaises(ValueError):consumer.select_runtime(value,rid)
        del value['runtimes']['linux-arm64']
        with self.assertRaises(ValueError):consumer.select_runtime(value,'linux-arm64')

    def test_malformed_opposing_or_abi_mismatched_record_is_rejected(self):
        for key,bad in [('rid','linux-arm64'),('abi',62),('abi',True),('hostSha256','a'*63),('providerSha256','B'*64)]:
            value=aggregate();value['runtimes']['linux-x64'][key]=bad
            with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):consumer.select_runtime(value,'linux-x64')
        for key,bad in [('schemaVersion',3),('hostBundled',True),('abi',62),('runtimes',None)]:
            value=aggregate();value[key]=bad
            with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):consumer.select_runtime(value,'linux-x64')

    def test_output_requires_exact_selected_hash_and_architecture_without_host(self):
        import hashlib
        data=bytearray(64);data[:6]=b'\x7fELF\x02\x01';data[18:20]=(62).to_bytes(2,'little')
        record=dict(rid='linux-x64',providerSha256=hashlib.sha256(data).hexdigest())
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);module=folder/'libRanvierWebCoreAtspi.so';module.write_bytes(data)
            consumer.verify_selected_asset(folder,record)
            opposing=dict(record,rid='linux-arm64')
            with self.assertRaises(ValueError):consumer.verify_selected_asset(folder,opposing)
            with self.assertRaises(ValueError):consumer.verify_selected_asset(folder,dict(record,providerSha256='0'*64))
            (folder/'libRanvierWebCoreHost.so').write_bytes(b'never loaded')
            with self.assertRaises(ValueError):consumer.verify_selected_asset(folder,record)


if __name__=='__main__':unittest.main()
