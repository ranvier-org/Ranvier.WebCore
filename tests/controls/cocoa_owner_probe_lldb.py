"""Observe the produced JSC's actual false-owner branch; no fixed addresses."""
import json
import re

armed = {}


def branch_plan(instructions):
    plans = []
    for i in range(len(instructions) - 2):
        call, branch, following = instructions[i:i + 3]
        if call['mnemonic'] != 'bl' or 'isCurrent' not in call['comment']:
            continue
        operands = re.sub(r'\s+', '', branch['operands'])
        match = re.fullmatch(r'w0,#(?:0x)?0,(0x[0-9a-f]+)', operands)
        if branch['mnemonic'] not in {'tbz', 'tbnz'} or not match:
            raise ValueError('Unqualified isCurrent conditional instruction')
        if branch['mnemonic'] == 'tbz':
            targets = [row for row in instructions if row.get('loadAddress') == int(match[1], 16)]
            if len(targets) != 1:
                raise ValueError('Unqualified false-owner taken target')
            failure = targets[0]
        else:
            failure = following
        if failure['mnemonic'] != 'bl' or not re.fullmatch(r'0x[0-9a-f]+', failure['operands']):
            raise ValueError('Unqualified false-owner fallthrough')
        plans.append({'call': call, 'branch': branch, 'failure': failure,
                      'falseEdge': 'taken' if branch['mnemonic'] == 'tbz' else 'fallthrough'})
    if len(plans) != 1:
        raise ValueError('Require one symbol-resolved isCurrent/false-owner path')
    return plans[0]


def before_destroy(frame, location, _):
    import lldb
    target = frame.GetThread().GetProcess().GetTarget()
    process = frame.GetThread().GetProcess()
    module = target.FindModule(lldb.SBFileSpec('libJavaScriptCore.dylib'))
    if not module.IsValid():
        raise RuntimeError('Produced JSC is not loaded')
    candidates = {}
    for symbol in module:
        name = symbol.GetName() or ''
        if name == 'WTF::RunLoop::TimerBase::~TimerBase()':
            candidates[symbol.GetStartAddress().GetFileAddress()] = symbol
    if not candidates:
        raise RuntimeError('Produced JSC destructor symbols unavailable')
    for symbol in candidates.values():
        rows = []
        for instruction in symbol.GetInstructions(target):
            address = instruction.GetAddress()
            error = lldb.SBError()
            value = process.ReadMemory(address.GetLoadAddress(target), instruction.GetByteSize(), error)
            if not error.Success():
                raise RuntimeError('Cannot read actual destructor instruction')
            rows.append({'fileAddress': address.GetFileAddress(), 'loadAddress': address.GetLoadAddress(target),
                         'mnemonic': instruction.GetMnemonic(target), 'operands': instruction.GetOperands(target),
                         'comment': instruction.GetComment(target) or '', 'bytes': value.hex()})
        if not any(row['mnemonic'] == 'bl' and 'isCurrent' in row['comment'] for row in rows):
            continue
        print('OWNER_DESTRUCTOR_INSTRUCTIONS=' + json.dumps(rows), flush=True)
        plan = branch_plan(rows)
        callee = target.ResolveLoadAddress(int(plan['failure']['operands'], 16))
        if callee.GetModule().GetUUIDString() != module.GetUUIDString():
            raise RuntimeError('False-owner assertion leaves the produced JSC')
        fatal = []
        for instruction in target.ReadInstructions(callee, 24):
            if instruction.GetMnemonic(target) == 'brk' and instruction.GetOperands(target) == '#0xbb08':
                fatal.append(instruction)
            if instruction.GetMnemonic(target) in ['ret', 'retab']:
                break
        if len(fatal) != 1:
            raise RuntimeError('False-owner callee lacks the qualified fatal instruction')
        instruction = fatal[0]
        error = lldb.SBError()
        value = process.ReadMemory(instruction.GetAddress().GetLoadAddress(target), 4, error)
        if not error.Success() or value != bytes.fromhex('006137d4'):
            raise RuntimeError('Actual fatal instruction bytes differ')
        branch = target.ResolveLoadAddress(plan['branch']['loadAddress'])
        key = branch.GetLoadAddress(target)
        if key not in armed:
            breakpoint = target.BreakpointCreateBySBAddress(branch)
            if not breakpoint.IsValid() or breakpoint.GetNumLocations() != 1:
                raise RuntimeError('Could not arm actual owner branch')
            armed[key] = {**plan, 'fatalFileAddress': hex(instruction.GetAddress().GetFileAddress()),
                          'fatalInstructionBytes': value.hex(), 'jscUUID': module.GetUUIDString()}
    if not armed:
        raise RuntimeError('No inspected destructor exposes the qualified owner branch')
    print('OWNER_BRANCH_ARMED=' + json.dumps(list(armed.values())), flush=True)
    return False


def verify(debugger):
    target = debugger.GetSelectedTarget()
    process = target.GetProcess()
    thread = process.GetSelectedThread()
    frame = thread.GetFrameAtIndex(0)
    if frame.GetPC() not in armed:
        raise RuntimeError('Inferior did not stop on the inspected ownership branch')
    register = frame.FindRegister('w0')
    if not register.IsValid() or register.GetValueAsUnsigned() & 1:
        raise RuntimeError('Actual isCurrent result is not false')
    frames = [item.GetFunctionName() or '' for item in thread]
    if not all(any(name in value for value in frames) for name in ['TimerBase', 'destroy_unchecked', '_pthread_start']):
        raise RuntimeError('Owner violation stack identity mismatch')
    selected = armed[frame.GetPC()]
    result = {'verified': True, 'isCurrentResultBit': 0, 'threadId': thread.GetThreadID(), 'frames': frames,
              'branchFileAddress': hex(selected['branch']['fileAddress']), 'fatalInstruction': 'brk #0xbb08',
              'actualInstructions': selected,
              'scope': 'Direct observation for this exact loaded JSC; subsequent isolated SIGKILL remains contextual'}
    print('OWNER_BRANCH_PROOF=' + json.dumps(result), flush=True)
