"""Copy a private source snapshot and add test-only phase fault hooks.

The input snapshot contains source/host and engine directories from a captured
private build recipe. Compile only the output copy; no public header or packaged
library gains these exports. Test cases are in phase_faults.py.
"""
from pathlib import Path
import argparse
import shutil

if globals().get('__name__') == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-snapshot', required=True, type=Path)
    parser.add_argument('--output-snapshot', required=True, type=Path)
    args = parser.parse_args()
    origin = args.input_snapshot.resolve()
    work = args.output_snapshot.resolve()
    if work == origin or origin in work.parents or work in origin.parents:
        parser.error('input and output snapshots must be separate directories')
    work.mkdir(parents=True, exist_ok=False)
    shutil.copytree(origin / 'source/host', work / 'source/host')
    shutil.copytree(origin / 'engine', work / 'engine')


host = work / 'source/host/RanvierWebCoreAbi.cpp'
source = host.read_text()
declarations = '''
extern "C" bool rv_test_ime_validation_ok();
extern "C" int rv_test_ime_failure_kind();
extern "C" void rv_test_ime_phase(int, int, int);
'''
source = source.replace('#include "config.h"', '#include "config.h"\n' + declarations, 1)
start = source.index('Function<bool()> validContext = [&] {')
stop = source.index('            };', start)
section = source[start:stop]
assert section.count('return !host->destroyAfterEditing') == 1
section = section.replace('return !host->destroyAfterEditing', 'return rv_test_ime_validation_ok() && !host->destroyAfterEditing')
source = source[:start] + section + source[stop:]
source += '''
static void (*rvTestImePhaseCallback)(int, int, int);
static bool rvTestImeValidationFailed;
static int rvTestImeFailureKind;
extern "C" RV_EXPORT void rv_test_ime_fault_install(void (*callback)(int, int, int))
{
    rvTestImePhaseCallback = callback;
    rvTestImeValidationFailed = false;
    rvTestImeFailureKind = 0;
}
extern "C" RV_EXPORT void rv_test_ime_fault_stop() { rvTestImeValidationFailed = true; }
extern "C" RV_EXPORT void rv_test_ime_set_failure_kind(int kind) { rvTestImeFailureKind = kind; }
extern "C" bool rv_test_ime_validation_ok() { return !rvTestImeValidationFailed; }
extern "C" int rv_test_ime_failure_kind() { return rvTestImeFailureKind; }
extern "C" void rv_test_ime_phase(int phase, int index, int count)
{
    if (rvTestImePhaseCallback)
        rvTestImePhaseCallback(phase, index, count);
}
extern "C" RV_EXPORT int32_t rv_test_ime_actual_text(RvHost* host, char* buffer, int32_t capacity, int32_t* length)
{
    if (!host || !liveHosts.contains(host))
        return RV_ERR_DETACHED;
    RefPtr target = host->document().focusedElement();
    RefPtr editable = imeEditable(target.get());
    return editable ? copyString(plainText(makeRangeSelectingNodeContents(*editable)), buffer, capacity, length) : RV_ERR_UNSUPPORTED;
}
'''
host.write_text(source)

composite = work / 'engine/CompositeEditCommand.cpp'
source = composite.read_text().replace('#include "config.h"', '#include "config.h"\n' + declarations, 1)
start = source.index('bool EditCommandComposition::unapplyForCompositionSuspension(')
stop = source.index('void EditCommandComposition::unapply()', start)
section = source[start:stop]
old = '        m_commands[i - 1]->doUnapply();'
assert section.count(old) == 1
section = section.replace(old, old + '\n        rv_test_ime_phase(1, m_commands.size() - i + 1, m_commands.size());')
source = source[:start] + section + source[stop:]
composite.write_text(source)

editor = work / 'engine/Editor.cpp'
source = editor.read_text().replace('#include "config.h"', '#include "config.h"\n' + declarations, 1)
start = source.index('bool Editor::deleteSurroundingComposition(')
stop = source.index('Editor::Editor(Document& document)', start)
section = source[start:stop]
old = '''    if (!oldComposition->unapplyForCompositionSuspension(validContext))
        return false;'''
assert section.count(old) == 1
section = section.replace(old, old + '\n    rv_test_ime_phase(2, 0, 0);')
section = section.replace('if (plainText(makeRangeSelectingNodeContents(editable)) != originalText)',
                          'if (rv_test_ime_failure_kind() == 4 || plainText(makeRangeSelectingNodeContents(editable)) != originalText)')
old = '    auto selectedRange = selectedOriginal.firstRange();'
assert section.count(old) == 1
section = section.replace(old, '''    rv_test_ime_phase(5, 0, 0);
    auto selectedRange = selectedOriginal.firstRange();
    if (rv_test_ime_failure_kind() == 5)
        selectedRange = std::nullopt;''')
section = section.replace('    acceptedDeletion->apply();', '    acceptedDeletion->apply();\n    rv_test_ime_phase(3, 0, 0);')
section = section.replace('if (plainText(makeRangeSelectingNodeContents(editable)) != expected)',
                          'if (rv_test_ime_failure_kind() == 2 || plainText(makeRangeSelectingNodeContents(editable)) != expected)')
section = section.replace('    TypingCommand::rebuildComposition(document, preedit);', '    TypingCommand::rebuildComposition(document, preedit);\n    rv_test_ime_phase(4, 0, 0);')
section = section.replace('    if (!inserted || inserted->start.container.ptr()',
                          '    if (rv_test_ime_failure_kind() == 3 || !inserted || inserted->start.container.ptr()')
source = source[:start] + section + source[stop:]
editor.write_text(source)
