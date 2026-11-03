"""Read invalidation arguments and stacks without evaluating target expressions."""
import json
import struct
import lldb

hits=0

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
                       'module':item.GetModule().GetFileSpec().GetFilename()})
        if len(frames)>=18:
            break
    print('MAC_INVALIDATE_STACK '+json.dumps({'hit':hits,'symbol':frame.GetDisplayFunctionName(),
          'x0':frame.FindRegister('x0').GetValueAsUnsigned(),'x1':pointer,'rect':rect,'frames':frames}),flush=True)
    return False
