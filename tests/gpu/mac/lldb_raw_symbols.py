"""LLDB helpers: resolve verified file addresses in loaded packaged modules only.

Import from the existing controller after the target's modules are loaded. A nearest
symbol is only a hint: the raw symbol table does not provide function extents.
"""
import bisect
import gzip
import json
import lldb

def load_verified_map(proof_path, map_path):
    import hashlib
    with open(proof_path, encoding='utf-8') as f:
        proof = json.load(f)
    with open(map_path, 'rb') as f:
        if hashlib.sha256(f.read()).hexdigest() != proof['symbolMapSha256']:
            raise ValueError('symbol map hash mismatch')
    with gzip.open(map_path, 'rt', encoding='utf-8') as f:
        maps = json.load(f)
    if set(maps) != set(proof['pairs']): raise ValueError('module map mismatch')
    for name, data in maps.items():
        pair = proof['pairs'][name]
        if not pair['textBytesEqual'] or data['uuid'] != pair['uuid']:
            raise ValueError('unverified module: ' + name)
    return proof, maps

def loaded_module(target, uuid):
    matches = []
    for i in range(target.GetNumModules()):
        module = target.GetModuleAtIndex(i)
        actual = (module.GetUUIDString() or '').replace('-', '').lower()
        if actual == uuid.lower(): matches.append(module)
    if len(matches) != 1: raise ValueError('expected one loaded module for UUID ' + uuid)
    return matches[0]

def install_host_breakpoints(target, proof):
    host = loaded_module(target, proof['pairs']['libRanvierWebCoreHost.dylib']['uuid'])
    result = {}
    for symbol, file_address in proof['hostEntries'].items():
        address = host.ResolveFileAddress(file_address)
        if not address.IsValid(): raise ValueError('unresolved file address: ' + symbol)
        load_address = address.GetLoadAddress(target)
        if load_address == lldb.LLDB_INVALID_ADDRESS: raise ValueError('module not loaded: ' + symbol)
        bp = target.BreakpointCreateByAddress(load_address)
        if not bp.IsValid() or bp.GetNumLocations() != 1:
            raise ValueError('breakpoint unresolved: ' + symbol)
        result[symbol] = bp
    return result

def annotate_frame(frame, proof, maps):
    address = frame.GetPCAddress()
    module = address.GetModule()
    uuid = (module.GetUUIDString() or '').replace('-', '').lower()
    matching = [(name, data) for name, data in maps.items() if data['uuid'] == uuid]
    if len(matching) != 1: return None
    name, data = matching[0]
    pc = address.GetFileAddress()
    text = proof['pairs'][name]['text']
    if not text['address'] <= pc < text['address'] + text['size']: return None
    rows = data['symbols']
    index = bisect.bisect_right(rows, [pc, chr(0x10ffff)]) - 1
    if index < 0: return None
    value, symbol = rows[index]
    return {'module': name, 'moduleUuid': uuid, 'filePC': pc, 'nearestRawTextSymbol': symbol,
            'offsetFromSymbol': pc-value, 'interpretation': 'nearest address only; not a verified function extent'}
