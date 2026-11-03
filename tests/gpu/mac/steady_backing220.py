"""Bound initial backing allocation and reject steady animation base repaints."""
import hashlib
import importlib.util
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('counter_control',Path(__file__).with_name('dirty220_replay.py'))
replay=importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)
replay.SOURCE_TREES=dict(replay.SOURCE_TREES,**{'tests/abi':'2f2d4ed80003b4feab49e9c08a6d5728124eeb3e'})

def transform(original):
    replacements=[
        ('bool counterDiagnostics;', 'bool counterDiagnostics;\nbool forceSteadyRepaint;'),
        ('auto stablePaints = basePaints;', 'auto stablePaints = basePaints;\n    auto animationPaints = basePaints;\n    unsigned animationStep = 0;'),
        ('for (int milliseconds : { 1000, 0 })', 'for (int milliseconds : { '+', '.join(['1000','0']*16)+' })'),
        ('        require(rv_animation_seek(animation.get(), milliseconds) == RV_OK, "seek compositor animation");',
         '        if (forceSteadyRepaint && animationStep == 1) {\n'
         '            using Node = std::unique_ptr<RvNode, decltype(&rv_node_release)>;\n'
         '            Node document(rv_host_document(host.get()), rv_node_release);\n'
         '            require(document != nullptr, "negative control document");\n'
         '            int32_t status = 0;\n'
         '            Node html(rv_node_query_selector(document.get(), "html", &status), rv_node_release);\n'
         '            require(status == RV_OK && html != nullptr, "negative control root element");\n'
         '            const char style[] = "background:rgb(254,254,254)";\n'
         '            require(rv_element_set_attribute(html.get(), "style", reinterpret_cast<const uint8_t*>(style), sizeof(style) - 1) == RV_OK, "negative control base damage");\n'
         '        }\n'
         '        require(rv_animation_seek(animation.get(), milliseconds) == RV_OK, "seek compositor animation");'),
        ('        require(counterResult == RV_OK && basePaints == stablePaints && readback == 0, "transform and opacity animation reuse base backing");',
         '        require(counterResult == RV_OK && readback == 0, "animation uses GPU frames without host readback");\n'
         '        if (!animationStep) {\n'
         '            require(basePaints >= stablePaints && basePaints <= stablePaints + 1, "first animated frame bounds one backing transition");\n'
         '            animationPaints = basePaints;\n'
         '        } else\n'
         '            require(basePaints == animationPaints, "transform and opacity animation reuse base backing");\n'
         '        ++animationStep;'),
        ('gpu == 8 && readback == 0', 'gpu == 38 && readback == 0'),
        ('native GPU frames8 with host readback frames0', 'native GPU frames38 with host readback frames0'),
        ('counterDiagnostics = diagnostic;', 'counterDiagnostics = diagnostic;\n            forceSteadyRepaint = argc == 2 && std::strcmp(argv[1], "--force-steady-repaint") == 0;'),
    ]
    source=original
    for before,after in replacements:
        if source.count(before)!=1: raise ValueError('Ambiguous replacement: '+before)
        source=source.replace(before,after)
    return source,replacements

def experiment(run,program,output,record):
    row,text=run('original-two-host-control',[program,'--diagnostic-scales','1,1'],allow_failure=True)
    negative=row['exit']==1 and 'transform and opacity animation reuse base backing' in text
    record['groups'].append({'group':'original-negative-control','exit':0 if negative else 1,'actualConsumerExit':row['exit']})
    if not negative: raise ValueError('The original negative control did not reproduce.')
    original=(ROOT/'tests/gpu/mac/spike.mm').read_text(encoding='utf-8')
    source,replacements=transform(original)
    candidate=output/'steady-backing.mm';candidate.write_text(source,encoding='utf-8')
    record['fixtureExperiment']={'originalSourceSha256':hashlib.sha256(original.encode()).hexdigest(),
        'candidateSourceSha256':replay.sha(candidate),'replacements':[{'before':a,'after':b} for a,b in replacements],
        'scope':'First validated animation frame permits at most one backing setup paint; subsequent31frames require no base repaint. Zero host readback and all pixel/lifetime checks remain hard. No frame discarded.'}
    command=list(next(item['command'] for item in record['steps'] if item['name']=='counter-compile'))
    command[command.index(str(ROOT/'tests/gpu/mac/spike.mm'))]=str(candidate)
    variant=output/'steady-backing';command[command.index('-o')+1]=str(variant)
    command.append('-I'+str(ROOT/'tests/gpu/mac'))
    run('steady-backing-compile',command)
    images=output/'steady-backing-images';images.mkdir()
    cases=[('default',['--output',str(images)]),('software-reject',['--reject-software'])]
    cases.extend(('scales-'+value.replace(',','_'),['--diagnostic-scales',value]) for value in ('1,1','1.5,1','1,1.5'))
    for name,args in cases:
        row,_=run('steady-backing-'+name,[variant,*args],allow_failure=True)
        record['groups'].append({'group':'steady-backing-'+name,'exit':row['exit']})
    row,text=run('forced-steady-repaint',[variant,'--force-steady-repaint'],allow_failure=True)
    rejected=row['exit']==1 and 'transform and opacity animation reuse base backing' in text
    record['groups'].append({'group':'forced-steady-repaint-negative-control','exit':0 if rejected else 1,
                             'actualConsumerExit':row['exit'],'steadyRepaintRejected':rejected})

if __name__=='__main__':
    replay.run_cases=experiment
    raise SystemExit(replay.main())
