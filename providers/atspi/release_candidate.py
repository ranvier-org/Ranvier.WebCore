"""Bind an aggregate artifact and SDK layout receipts for independent release review; never publish."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('atspi_candidate_policy',ROOT/'public_aggregate.py')
aggregate=importlib.util.module_from_spec(spec);spec.loader.exec_module(aggregate)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record_candidate(aggregate_receipt,cohort_file,layouts):
    cohort=json.loads(Path(cohort_file).read_bytes());aggregate.validate_policy(cohort)
    if set(layouts)!=set(aggregate.RIDS):raise ValueError('Require both independently selected SDK RID layouts.')
    record=json.loads(Path(aggregate_receipt).read_bytes())
    package=Path(record['path'])
    if digest(package)!=record['sha256']:raise ValueError('Aggregate package bytes changed.')
    with zipfile.ZipFile(package) as archive:
        if archive.namelist().count('provider-manifest.json')!=1:raise ValueError('Ambiguous aggregate manifest.')
        manifest=json.loads(archive.read('provider-manifest.json'))
    expected=dict(id=cohort['id'],version=cohort['version'],nativeVersion=cohort['nativeVersion'],abi=63,
                  callerClaimedNativeSourceRevision=cohort['nativeSource'],callerClaimedProviderSourceRevision=cohort['providerSourceClaim'],
                  sourceProvenance='unverified-caller-claim',hostBundled=False,schemaVersion=2)
    if manifest!=record['manifest'] or any(manifest.get(key)!=value for key,value in expected.items()):
        raise ValueError('Aggregate metadata differs from its selected cohort or producer record.')
    runtimes=manifest.get('runtimes',{})
    if set(runtimes)!=set(aggregate.RIDS):raise ValueError('The aggregate lacks its two RID records.')
    sdk={}
    for rid,path in layouts.items():
        runtime=runtimes[rid];pins=cohort['rids'][rid]
        if runtime.get('inputPackageSha256')!=pins['packageSha256'] or runtime.get('qualificationReceiptSha256')!=pins['receiptSha256']:
            raise ValueError('Aggregate qualification input identity differs.')
        layout=json.loads(Path(path).read_bytes())
        if (layout.get('packageSha256')!=record['sha256'] or layout.get('selectedRid')!=rid
                or layout.get('selectedRuntime')!=runtime or layout.get('executed') is not False or layout.get('consumer') is not None):
            raise ValueError('SDK layout receipt differs or claims execution in a layout-only stage.')
        sdk[rid]=dict(receiptSha256=digest(path),scope='ordinary SDK asset selection only; actual per-RID renderer/protocol/AOT qualification is separately retained',executed=False)
    return dict(schemaVersion=1,publicationEnabled=False,scope='Artifact candidate for independent review; SDK layout is not renderer or ARM execution proof, and no publication is performed',
                package=dict(id=cohort['id'],version=cohort['version'],filename=package.name,sha256=record['sha256']),
                nativeVersion=cohort['nativeVersion'],callerClaimedNativeSourceRevision=cohort['nativeSource'],
                callerClaimedProviderSourceRevision=cohort['providerSourceClaim'],sourceProvenance='unverified-caller-claim',
                cohortFileSha256=digest(cohort_file),aggregateReceiptSha256=digest(aggregate_receipt),qualificationInputs=cohort['rids'],sdkLayout=sdk)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aggregate-receipt',type=Path,required=True)
    parser.add_argument('--cohort',type=Path,required=True)
    parser.add_argument('--x64-layout',type=Path,required=True)
    parser.add_argument('--arm64-layout',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    record=record_candidate(args.aggregate_receipt,args.cohort,{'linux-x64':args.x64_layout,'linux-arm64':args.arm64_layout})
    with args.output.open('x',encoding='utf-8') as stream:json.dump(record,stream,indent=2)
    print(json.dumps(record))
