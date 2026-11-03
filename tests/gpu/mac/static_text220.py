"""Compare static text layer hints using the unchanged retained native cohort."""
import hashlib
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('dirty220_control',Path(__file__).with_name('dirty220_replay.py'))
replay=importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)
BEFORE='color:black;transform:translateZ(0)'
AFTER='color:black;will-change:transform;transform:translateZ(0)'
LABEL='static-text-hint'
SCOPE='Static glyph backing hint only; original native cohort unchanged.'

def experiment(run,program,output,record):
    row,text=run('original-two-host-control',[program,'--diagnostic-scales','1,1'],allow_failure=True)
    negative=row['exit']==1 and 'transform and opacity animation reuse base backing' in text
    record['groups'].append({'group':'original-two-host-negative-control','exit':0 if negative else 1,
                             'actualConsumerExit':row['exit'],'originalStrictFailureRetained':negative})
    if not negative:
        raise ValueError('The original strict negative control no longer reproduces.')
    original=(ROOT/'tests/gpu/mac/spike.mm').read_text(encoding='utf-8')
    before=BEFORE
    after=AFTER
    if original.count(before)!=1:
        raise ValueError('Ambiguous static text style replacement.')
    candidate=original.replace(before,after)
    source=output/(LABEL+'.mm')
    source.write_text(candidate,encoding='utf-8')
    record['fixtureExperiment']={'originalSourceSha256':hashlib.sha256(original.encode()).hexdigest(),
                                 'candidateSourceSha256':replay.sha(source),'replacementBefore':before,
                                 'replacementAfter':after,'replacements':1,'originalAssertionsPreserved':True,
                                 'additionalAssertions':after.count('require(')-before.count('require('),
                                 'warmupAdded':False,'scope':SCOPE}
    command=next(item['command'] for item in record['steps'] if item['name']=='counter-compile')
    command=list(command)
    command[command.index(str(ROOT/'tests/gpu/mac/spike.mm'))]=str(source)
    variant=output/LABEL
    command[command.index('-o')+1]=str(variant)
    command.append('-I'+str(ROOT/'tests/gpu/mac'))
    run(LABEL+'-compile',command)
    images=output/(LABEL+'-images')
    images.mkdir()
    cases=[('default',['--output',str(images)]),('software-reject',['--reject-software'])]
    cases.extend(('scales-'+value.replace(',','_'),['--diagnostic-scales',value])
                 for value in ('1,1','1.5,1','1,1.5'))
    for name,args in cases:
        row,_=run(LABEL+'-'+name,[variant,*args],allow_failure=True)
        record['groups'].append({'group':LABEL+'-'+name,'exit':row['exit']})

if __name__=='__main__':
    replay.run_cases=experiment
    raise SystemExit(replay.main())
