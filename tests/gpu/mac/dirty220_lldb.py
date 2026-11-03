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
    target.FindBreakpointByID(1).SetEnabled(False)

def on_invalidate(frame,location,internal_dict):
    global hits
    hits+=1
    thread=frame.GetThread()
    process=thread.GetProcess()
    pointer=frame.FindRegister('x1').GetValueAsUnsigned()
    error=lldb.SBError()
    data=process.ReadMemory(pointer,16,error)
    rect=list(struct.unpack('<4i',data)) if error.Success() and len(data)==16 else None
    frames=[]
    for item in thread:
        address=item.GetPCAddress()
        frames.append({'function':item.GetDisplayFunctionName(),'pc':address.GetLoadAddress(frame.GetThread().GetProcess().GetTarget()),
                       'module':item.GetModule().GetFileSpec().GetFilename(),
                       'rawSymbolHint':lldb_raw_symbols.annotate_frame(item,proof,maps)})
        if len(frames)>=18:
            break
    print('MAC_INVALIDATE_STACK '+json.dumps({'hit':hits,'breakpointId':location.GetBreakpoint().GetID(),'symbol':frame.GetDisplayFunctionName(),
          'x0':frame.FindRegister('x0').GetValueAsUnsigned(),'x1':pointer,'rect':rect,'frames':frames}),flush=True)
    return False
