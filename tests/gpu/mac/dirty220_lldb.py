"""Read invalidation arguments and stacks without evaluating target expressions."""
import json
import struct
import lldb
import pathlib
import sys

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import lldb_raw_symbols

hits=0
proof=None
maps=None
layout_hits=0
layout_entries={}

def install(debugger):
    global proof,maps
    directory=pathlib.Path(__file__).resolve().parent
    proof,maps=lldb_raw_symbols.load_verified_map(directory/'proof.json',directory/'raw-text-symbols.json.gz')
    target=debugger.GetSelectedTarget()
    process=target.GetProcess()
    if process.GetState()!=lldb.eStateStopped:
        raise ValueError('Target did not stop at main.')
    entries=lldb_raw_symbols.install_host_breakpoints(target,proof)
    for name,bp in entries.items():
        bp.SetScriptCallbackFunction('dirty220_lldb.on_invalidate')
        print('MAC_ADDRESS_BREAKPOINT '+json.dumps({'symbol':name,'locations':bp.GetNumLocations(),'id':bp.GetID()}),flush=True)
    engine=lldb_raw_symbols.loaded_module(target,proof['pairs']['libWebCore.dylib']['uuid'])
    for symbol in ('__ZN7WebCore10RenderView21accumulateRepaintRectENS_7IntRectES1_',
                   '__ZN7WebCore12RenderObject14setNeedsLayoutENS_15MarkingBehaviorE',
                   '__ZN7WebCore21RenderLayerCompositor40updateRepaintRectsAfterCompositingChangeERNS_11RenderLayerEbRNS0_19BackingSharingStateE',
                   '__ZN7WebCore21RenderLayerCompositor23updateCompositingPolicyEv'):
        rows=[address for address,name in maps['libWebCore.dylib']['symbols'] if name==symbol]
        if len(rows)!=1:
            raise ValueError('Ambiguous layout entry: '+symbol)
        address=engine.ResolveFileAddress(rows[0])
        if not address.IsValid() or address.GetLoadAddress(target)==lldb.LLDB_INVALID_ADDRESS:
            raise ValueError('Unloaded layout entry: '+symbol)
        bp=target.BreakpointCreateByAddress(address.GetLoadAddress(target))
        if not bp.IsValid() or bp.GetNumLocations()!=1:
            raise ValueError('Unresolved layout breakpoint: '+symbol)
        bp.SetScriptCallbackFunction('dirty220_lldb.on_layout')
        layout_entries[bp.GetID()]=symbol
        print('MAC_LAYOUT_BREAKPOINT '+json.dumps({'symbol':symbol,'fileAddress':rows[0],'id':bp.GetID()}),flush=True)
    target.FindBreakpointByID(1).SetEnabled(False)

def stack_frames(frame):
    target=frame.GetThread().GetProcess().GetTarget()
    return [{'function':item.GetDisplayFunctionName(),'pc':item.GetPCAddress().GetLoadAddress(target),
             'module':item.GetModule().GetFileSpec().GetFilename(),
             'rawSymbolHint':lldb_raw_symbols.annotate_frame(item,proof,maps)} for item in list(frame.GetThread())[:18]]

def on_layout(frame,location,internal_dict):
    global layout_hits
    layout_hits+=1
    breakpoint_id=location.GetBreakpoint().GetID()
    symbol=layout_entries[breakpoint_id]
    policy=None
    if 'RenderLayerCompositor' in symbol:
        error=lldb.SBError()
        data=frame.GetThread().GetProcess().ReadMemory(frame.FindRegister('x0').GetValueAsUnsigned()+0x7d,1,error)
        if not error.Success() or len(data)!=1:
            raise ValueError('Cannot read verified compositor policy byte.')
        policy=data[0]
    print('MAC_LAYOUT_STACK '+json.dumps({'hit':layout_hits,'breakpointId':breakpoint_id,'entry':symbol,
          'compositorPolicyByte':policy,
          'registers':{name:frame.FindRegister(name).GetValueAsUnsigned() for name in ('x0','x1','x2','x3','x4')},
          'frames':stack_frames(frame)}),flush=True)
    return False

def on_invalidate(frame,location,internal_dict):
    global hits
    hits+=1
    thread=frame.GetThread()
    process=thread.GetProcess()
    pointer=frame.FindRegister('x1').GetValueAsUnsigned()
    error=lldb.SBError()
    data=process.ReadMemory(pointer,16,error)
    rect=list(struct.unpack('<4i',data)) if error.Success() and len(data)==16 else None
    frames=stack_frames(frame)
    print('MAC_INVALIDATE_STACK '+json.dumps({'hit':hits,'breakpointId':location.GetBreakpoint().GetID(),'symbol':frame.GetDisplayFunctionName(),
          'x0':frame.FindRegister('x0').GetValueAsUnsigned(),'x1':pointer,'rect':rect,'frames':frames}),flush=True)
    return False
