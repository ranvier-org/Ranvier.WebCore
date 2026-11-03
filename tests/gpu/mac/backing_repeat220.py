"""Collect every backing-reuse failure while keeping pixel and lifetime gates hard."""
import hashlib
import importlib.util
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('counter_control',Path(__file__).with_name('dirty220_replay.py'))
replay=importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)
replay.SOURCE_TREES=dict(replay.SOURCE_TREES,**{'tests/abi':'2f2d4ed80003b4feab49e9c08a6d5728124eeb3e'})

def experiment(run,program,output,record):
    row,text=run('original-two-host-control',[program,'--diagnostic-scales','1,1'],allow_failure=True)
    negative=row['exit']==1 and 'transform and opacity animation reuse base backing' in text
    record['groups'].append({'group':'original-negative-control','exit':0 if negative else 1,
                             'actualConsumerExit':row['exit'],'originalStrictFailureRetained':negative})
    if not negative:
        raise ValueError('The original strict negative control did not reproduce.')
    original=(ROOT/'tests/gpu/mac/spike.mm').read_text(encoding='utf-8')
    source=original
    replacements=[
        ('int assertions;', 'int assertions;\nint backingFailures;'),
        ('    if (!value)\n        throw',
         '    if (!value && std::strcmp(message, "transform and opacity animation reuse base backing") == 0) {\n'
         '        ++backingFailures;\n'
         '        std::fprintf(stderr, "MAC_COUNTER_ASSERTION_RED %s\\n", message);\n'
         '        return;\n'
         '    }\n'
         '    if (!value)\n        throw'),
        ('for (int milliseconds : { 1000, 0 })',
         'for (int milliseconds : { '+', '.join(['1000','0']*16)+' })'),
        ('gpu == 8 && readback == 0', 'gpu == 38 && readback == 0'),
        ('native GPU frames8 with host readback frames0', 'native GPU frames38 with host readback frames0'),
        ('            std::printf("MAC_GPU_SPIKE PASS assertions=',
         '            std::printf("MAC_COUNTER_LEDGER failed=%d cycles=%zu presented=%llu\\n", backingFailures, scales.size(), static_cast<unsigned long long>(presented));\n'
         '            if (backingFailures) return 1;\n'
         '            std::printf("MAC_GPU_SPIKE PASS assertions='),
    ]
    for before,after in replacements:
        if source.count(before)!=1:
            raise ValueError('Ambiguous diagnostic replacement: '+before)
        source=source.replace(before,after)
    candidate=output/'backing-repeat.mm'
    candidate.write_text(source,encoding='utf-8')
    record['fixtureExperiment']={'originalSourceSha256':hashlib.sha256(original.encode()).hexdigest(),
        'candidateSourceSha256':replay.sha(candidate),'replacements':[{'before':a,'after':b} for a,b in replacements],
        'seeksPerHost':32,'gpuFramesPerHost':38,'nativeProductQualified':False,
        'scope':'Original backing condition failures are logged and force exit1 at completion; every other assertion still fails immediately. No native changes or discarded frames.'}
    command=list(next(item['command'] for item in record['steps'] if item['name']=='counter-compile'))
    command[command.index(str(ROOT/'tests/gpu/mac/spike.mm'))]=str(candidate)
    variant=output/'backing-repeat'
    command[command.index('-o')+1]=str(variant)
    command.append('-I'+str(ROOT/'tests/gpu/mac'))
    run('backing-repeat-compile',command)
    images=output/'backing-repeat-images'
    images.mkdir()
    cases=[('default',['--output',str(images)]),('same-scale',['--diagnostic-scales','1,1'])]
    for name,args in cases:
        row,text=run('backing-repeat-'+name,[variant,*args],allow_failure=True)
        ledger=re.findall(r'MAC_COUNTER_LEDGER failed=(\d+) cycles=(\d+) presented=(\d+)',text)
        completed=len(ledger)==1 and row['exit']==(1 if int(ledger[0][0]) else 0)
        record['groups'].append({'group':'backing-repeat-'+name,'exit':0 if completed else 1,
                                 'actualConsumerExit':row['exit'],'ledger':ledger,'diagnosticOnly':True})

if __name__=='__main__':
    replay.run_cases=experiment
    raise SystemExit(replay.main())
