"""Direct native RSA/EC methods; public typed normalization is a separate contract."""
import argparse
import base64
import ctypes as C
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0,str(Path(__file__).resolve().parent))
from form_collections import Native, Case, P, I
from utf8_inputs import bind as bind_utf8

FIELDS=['kty','crv','x','y','d','n','e','p','q','dp','dq','qi','alg','use']
ALGORITHMS={'RS256':1,'PSS':2,'OAEP':3,'ECDSA':4,'ECDH':5}
OPERATIONS={'generate':1,'import':2,'export':3,'sign':4,'verify':5,'encrypt':6,'decrypt':7,'derive':8,'derive-import':9}
FORMATS={'raw':1,'jwk':2,'spki':3,'pkcs8':4}

class Bytes(C.Structure):
    _fields_=[('data',P),('length',I)]
class Request(C.Structure):
    _fields_=[(n,I) for n in ['size','algorithm','operation','format','hash','curve']]
    _fields_ += [('parameter',C.c_int64),('extractable',I),('usages',C.c_uint32),('key',P),('peer',P)]
    _fields_ += [(n,Bytes) for n in ['input','signature','label','exponent']]
    _fields_ += [('jwk',Bytes*14),('jwkExt',I)]
class Result(C.Structure):
    _fields_=[('size',I),('exceptionCode',I),('exceptionName',C.c_char_p)]
    _fields_ += [(n,I) for n in ['ownerThread','terminalCount','callbackDuringStart','borrowedRetains','verified','keyType','extractable']]
    _fields_ += [('usages',C.c_uint32),('modulusBits',I),('hashBits',I),('algorithm',I),('curve',I),('firstKey',P),('secondKey',P),('output',Bytes),('exponent',Bytes),('jwk',Bytes*14),('jwkExt',I)]
CALLBACK=C.CFUNCTYPE(None,P,C.POINTER(Result))

def b64(value): return base64.urlsafe_b64encode(value).decode().rstrip('=')
def decode(value): return base64.urlsafe_b64decode(value+'='*((-len(value))%4))
def copied(value):
    assert value.length >= 0 and (not value.length or value.data)
    return C.string_at(value.data,value.length)

class Backend:
    def __init__(self,directory,bridge_library=None):
        self.n=Native(directory)
        self.library=C.CDLL(bridge_library) if bridge_library else self.n.library
        self.start=bind_utf8(self.library,'ranvier_test_asymmetric_start',P,[P,P,CALLBACK,P])
        self.barrier=bind_utf8(self.library,'ranvier_test_asymmetric_barrier',I,[P])
        self.release=bind_utf8(self.library,'ranvier_test_asymmetric_release',I,[P])
        self.release_key=bind_utf8(self.library,'ranvier_test_asymmetric_key_release',I,[P])
        self.echo=bind_utf8(self.library,'ranvier_test_asymmetric_input',I,[P,I,C.POINTER(Bytes)])
        assert bind_utf8(self.library,'ranvier_test_asymmetric_request_size',I,[])()==C.sizeof(Request)
        assert bind_utf8(self.library,'ranvier_test_asymmetric_result_size',I,[])()==C.sizeof(Result)
        self.page=Case(self.n,'<p>script-free asymmetric backend qualification</p>')
        self.records,self.keys,self.callbacks=[],[],[]
        self.check_script_guard()
    def check_script_guard(self):
        assert self.n.call('rv_host_scripts_enabled',[P],self.page.host)==0
        assert self.n.call('rv_host_vm_entry_disallowed',[P],self.page.host)==1
    def pump(self):
        self.n.ok('rv_host_update',[P],self.page.host)
        assert self.n.call('rv_run_loop_cycle',[I],1)>=0
    def run(self,label,algorithm,operation,*,key=None,peer=None,format='raw',hash=256,curve=256,
            parameter=0,extractable=True,usages=0,data=b'',signature=b'',oaep_label=b'',exponent=b'\x01\x00\x01',jwk=None):
        request=Request()
        request.size,request.algorithm,request.operation=C.sizeof(Request),ALGORITHMS[algorithm],OPERATIONS[operation]
        request.format,request.hash,request.curve=FORMATS[format],hash,curve
        request.parameter,request.extractable,request.usages=parameter,extractable,usages
        request.key,request.peer,request.jwkExt=key,peer,-1
        buffers=[]
        def span(value):
            buffer=C.create_string_buffer(value)
            buffers.append(buffer)
            return Bytes(C.cast(buffer,P),len(value))
        inputs=[data,signature,oaep_label,exponent]
        for name,value in zip(['input','signature','label','exponent'],inputs): setattr(request,name,span(value))
        if jwk is not None:
            for i,name in enumerate(FIELDS):
                if name in jwk: request.jwk[i]=span(jwk[name].encode())
            if 'ext' in jwk: request.jwkExt=int(jwk['ext'])
        events,errors=[],[]
        def complete(_,pointer):
            try:
                r=pointer.contents
                assert r.size==C.sizeof(Result)
                value={n:int(getattr(r,n)) for n in ['exceptionCode','ownerThread','terminalCount','callbackDuringStart','borrowedRetains','verified','keyType','extractable','usages','modulusBits','hashBits','algorithm','curve']}
                value.update(exception=r.exceptionName.decode() if r.exceptionName else None,
                             firstKey=r.firstKey,secondKey=r.secondKey,output=copied(r.output).hex(),exponent=copied(r.exponent).hex())
                value['jwk']={name:copied(r.jwk[i]).decode() for i,name in enumerate(FIELDS) if r.jwk[i].data}
                if r.jwkExt>=0: value['jwk']['ext']=bool(r.jwkExt)
                for handle in [r.firstKey,r.secondKey]:
                    if handle: self.keys.append(handle)
                events.append(value)
            except Exception as error: errors.append(repr(error))
        callback=CALLBACK(complete)
        self.callbacks.append(callback)
        token=self.start(self.page.document,C.byref(request),callback,None)
        assert token,label+': request rejected'
        for buffer in buffers: C.memset(buffer,0xee,C.sizeof(buffer))
        try:
            echoed=[]
            for i,expected in enumerate(inputs):
                value=Bytes()
                assert self.echo(token,i,C.byref(value))==0
                actual=copied(value)
                assert actual==expected,label+': caller input not copied'
                echoed.append(dict(hex=actual.hex(),sha256=hashlib.sha256(actual).hexdigest()))
            deadline=time.monotonic()+120
            while not events and not errors and time.monotonic()<deadline: self.pump()
            assert events and not errors,(label,errors)
            assert self.barrier(token)==0
            for _ in range(5): self.pump()
            assert len(events)==1 and events[0]['terminalCount']==1 and events[0]['ownerThread'],(label,events)
            record=dict(label=label,algorithmName=algorithm,operationName=operation,copiedInputs=echoed,requestJwk=jwk,**events[0])
            self.records.append(record)
            return record
        finally:
            assert self.barrier(token)==0
            for _ in range(3): self.pump()
            assert self.release(token)==0,label+': operation remains pending'
    def close(self):
        for key in reversed(self.keys): assert self.release_key(key)==0
        self.keys.clear()
        self.check_script_guard()
        self.page.close()

def validate_fixture(path):
    fixture=json.loads(path.read_bytes())
    assert fixture['source']['sha256']=='939fab548a6e6bb49a5b3c4dd24a3c5df54a46645447b2d6f4df4fd88ff2d69f'
    assert [v['fieldBits'] for v in fixture['vectors']]==[256,384,521]
    for v in fixture['vectors']:
        width=(v['fieldBits']+7)//8
        assert v['widthBytes']==width and v['curve']=='P-'+str(v['fieldBits'])
        for side in ['initiator','responder']:
            assert set(v[side])=={'d','x','y'}
            for value in v[side].values(): assert len(bytes.fromhex(value))==width
        assert len(bytes.fromhex(v['sharedSecretHex']))==width
        assert len(bytes.fromhex(v['sharedPointYHex']))==width
    assert fixture['vectors'][2]['initiator']['d'].startswith('00')
    return fixture

def verify(directory,jws_path,ecdh_path,bridge_library=None):
    backend=Backend(directory,bridge_library)
    failures=[]
    def check(condition,label,detail):
        if not condition: failures.append(dict(label=label,detail=detail))
    def ok(result):
        check(result['exception'] is None,result['label'],result)
        return result
    def success(*args,**kwargs): return ok(backend.run(*args,**kwargs))
    def error(*args,expected='DataError',**kwargs):
        result=backend.run(*args,**kwargs)
        check(result['exception']==expected,result['label'],result)
        return result
    def import_key(label,algorithm,**kwargs):
        result=success(label,algorithm,'import',**kwargs)
        check(result['borrowedRetains']==1,label,'borrowed key callback retained')
        assert result['firstKey'],label+': import failed'
        return result['firstKey']
    def group(name,body):
        try: body()
        except Exception as ex:
            failures.append(dict(label=name,infrastructureFailure=repr(ex),traceback=traceback.format_exc()))
    def export_roundtrips(label,algorithm,public,private,curve=256):
        for which,key,usages in [('public',public,1 if algorithm=='OAEP' else 0 if algorithm=='ECDH' else 8),
                                 ('private',private,2 if algorithm=='OAEP' else 48 if algorithm=='ECDH' else 4)]:
            metadata=success(label+'/'+which+'/jwk',algorithm,'export',key=key,format='jwk',curve=curve)
            check(metadata['keyType']==(0 if which=='public' else 1),metadata['label'],'key type')
            check(metadata['usages']==usages,metadata['label'],'key usages')
            check(metadata['extractable']==1,metadata['label'],'extractable metadata')
            if algorithm in ['ECDSA','ECDH']: check(metadata['curve']==curve,metadata['label'],'named curve')
            else:
                check(metadata['modulusBits']==2048,metadata['label'],'modulus length')
                check(metadata['hashBits']==256,metadata['label'],'bound hash metadata')
                check(metadata['exponent']=='010001',metadata['label'],'public exponent')
            imported=import_key(label+'/'+which+'/import-jwk',algorithm,format='jwk',jwk=metadata['jwk'],usages=usages,curve=curve)
            again=success(label+'/'+which+'/jwk-again',algorithm,'export',key=imported,format='jwk',curve=curve)
            check(again['jwk']==metadata['jwk'],again['label'],'JWK roundtrip')
            der_format='spki' if which=='public' else 'pkcs8'
            der=success(label+'/'+which+'/'+der_format,algorithm,'export',key=key,format=der_format,curve=curve)
            encoded=bytes.fromhex(der['output'])
            check(encoded.startswith(b'\x30'),der['label'],'DER sequence')
            key2=import_key(label+'/'+which+'/import-'+der_format,algorithm,format=der_format,data=encoded,usages=usages,curve=curve)
            der2=success(label+'/'+which+'/der-again',algorithm,'export',key=key2,format=der_format,curve=curve)
            check(der2['output']==der['output'],der2['label'],'DER byte roundtrip')
            error(label+'/'+which+'/invalid-der',algorithm,'import',format=der_format,data=b'\x30\x00',usages=usages,curve=curve)
        if algorithm in ['ECDSA','ECDH']:
            raw=success(label+'/raw',algorithm,'export',key=public,format='raw',curve=curve)
            point=bytes.fromhex(raw['output'])
            check(len(point)==1+2*((curve+7)//8) and point[0]==4,raw['label'],'uncompressed point length')
            key=import_key(label+'/import-raw',algorithm,format='raw',data=point,usages=0 if algorithm=='ECDH' else 8,curve=curve)
            again=success(label+'/raw-again',algorithm,'export',key=key,format='raw',curve=curve)
            check(again['output']==raw['output'],again['label'],'raw point roundtrip')
            error(label+'/invalid-point',algorithm,'import',format='raw',data=b'\x04'+bytes(2*((curve+7)//8)),usages=0 if algorithm=='ECDH' else 8,curve=curve)
            error(label+'/invalid-jwk-point',algorithm,'import',format='jwk',jwk=dict(kty='EC',crv='P-'+str(curve),x=b64(bytes((curve+7)//8)),y=b64(bytes((curve+7)//8))),usages=0 if algorithm=='ECDH' else 8,curve=curve)
            error(label+'/truncated-point',algorithm,'import',format='raw',data=point[:-1],usages=0 if algorithm=='ECDH' else 8,curve=curve)
            error(label+'/invalid-point-prefix',algorithm,'import',format='raw',data=b'\x00'+point[1:],usages=0 if algorithm=='ECDH' else 8,curve=curve)
            error(label+'/private-raw',algorithm,'export',key=private,format='raw',curve=curve,expected='InvalidAccessError')
    try:
        jws=json.loads(jws_path.read_bytes())
        ecdh=validate_fixture(ecdh_path)
        for v in jws['vectors']:
            def published(v=v):
                algorithm='RS256' if v['algorithm']=='RS256' else 'ECDSA'
                private=import_key(v['id']+'/private',algorithm,format='jwk',jwk=v['jwk'],usages=4)
                public_jwk={k:value for k,value in v['jwk'].items() if k not in ['d','p','q','dp','dq','qi']}
                public=import_key(v['id']+'/public',algorithm,format='jwk',jwk=public_jwk,usages=8)
                message,signature=bytes.fromhex(v['signing_input_hex']),bytes.fromhex(v['signature_hex'])
                result=success(v['id']+'/published-verify',algorithm,'verify',key=public,data=message,signature=signature)
                check(result['verified']==1,result['label'],'published signature')
                for label,data,sig in [('message',message+b'!',signature),('signature',message,bytes([signature[0]^1])+signature[1:])]:
                    result=success(v['id']+'/tamper-'+label,algorithm,'verify',key=public,data=data,signature=sig)
                    check(result['verified']==0,result['label'],'tamper rejection')
                signed=success(v['id']+'/sign',algorithm,'sign',key=private,data=message)
                if algorithm=='RS256': check(signed['output']==v['signature_hex'],signed['label'],'deterministic RFC signature')
                result=success(v['id']+'/signed-verify',algorithm,'verify',key=public,data=message,signature=bytes.fromhex(signed['output']))
                check(result['verified']==1,result['label'],'generated signature roundtrip')
                error(v['id']+'/public-sign',algorithm,'sign',key=public,data=message,expected='InvalidAccessError')
                export_roundtrips(v['id'],algorithm,public,private)
            group(v['id'],published)
        for algorithm in ['RS256','PSS','OAEP']:
            def rsa(algorithm=algorithm):
                usages=3 if algorithm=='OAEP' else 12
                generated=success(algorithm+'/generate',algorithm,'generate',parameter=2048,usages=usages)
                public,private=generated['firstKey'],generated['secondKey']
                assert public and private
                export_roundtrips(algorithm,algorithm,public,private)
                if algorithm=='OAEP':
                    message,label=b'RSA OAEP backend\x00test',b'nonempty\x00label'
                    encrypted=success('OAEP/encrypt',algorithm,'encrypt',key=public,data=message,oaep_label=label)
                    encrypted=bytes.fromhex(encrypted['output'])
                    decrypted=success('OAEP/decrypt',algorithm,'decrypt',key=private,data=encrypted,oaep_label=label)
                    check(bytes.fromhex(decrypted['output'])==message,decrypted['label'],'OAEP label roundtrip')
                    error('OAEP/wrong-label',algorithm,'decrypt',key=private,data=encrypted,oaep_label=label+b'!',expected='OperationError')
                    error('OAEP/oversized',algorithm,'encrypt',key=public,data=bytes(256),expected='OperationError')
                else:
                    for salt in ([0,7,32] if algorithm=='PSS' else [0]):
                        signature=success(algorithm+'/sign/'+str(salt),algorithm,'sign',key=private,parameter=salt,data=b'native sign roundtrip')
                        result=success(algorithm+'/verify/'+str(salt),algorithm,'verify',key=public,parameter=salt,data=b'native sign roundtrip',signature=bytes.fromhex(signature['output']))
                        check(result['verified']==1,result['label'],'sign verify roundtrip')
                        if algorithm=='PSS':
                            wrong=success('PSS/wrong-salt/'+str(salt),algorithm,'verify',key=public,parameter=salt+1,data=b'native sign roundtrip',signature=bytes.fromhex(signature['output']))
                            check(wrong['verified']==0,wrong['label'],'PSS salt mismatch')
            group(algorithm,rsa)
        peers={}
        for bits in [256,384,521]:
            for algorithm in ['ECDSA','ECDH']:
                def ec(bits=bits,algorithm=algorithm):
                    label=algorithm+'/'+str(bits)
                    generated=success(label+'/generate',algorithm,'generate',curve=bits,usages=48 if algorithm=='ECDH' else 12)
                    public,private=generated['firstKey'],generated['secondKey']
                    assert public and private
                    export_roundtrips(label,algorithm,public,private,bits)
                    if algorithm=='ECDSA':
                        h=256 if bits==256 else 384 if bits==384 else 512
                        signed=success(label+'/sign',algorithm,'sign',key=private,data=b'ECDSA roundtrip',hash=h)
                        check(len(bytes.fromhex(signed['output']))==2*((bits+7)//8),signed['label'],'P1363 signature width')
                        result=success(label+'/verify',algorithm,'verify',key=public,data=b'ECDSA roundtrip',signature=bytes.fromhex(signed['output']),hash=h)
                        check(result['verified']==1,result['label'],'ECDSA roundtrip')
                    else:
                        peers[bits]=(public,private)
                        second=success(label+'/generate-peer',algorithm,'generate',curve=bits,usages=48)
                        a=success(label+'/mutual-a',algorithm,'derive',key=private,peer=second['firstKey'],parameter=-1)
                        b=success(label+'/mutual-b',algorithm,'derive',key=second['secondKey'],peer=public,parameter=-1)
                        check(a['output']==b['output'] and len(bytes.fromhex(a['output']))==(bits+7)//8,label,'generated mutual parity (not published answer)')
                        error(label+'/private-peer',algorithm,'derive',key=private,peer=second['secondKey'],parameter=-1,expected='InvalidAccessError')
                group(algorithm+'/'+str(bits),ec)
        for v in ecdh['vectors']:
            def published_ecdh(v=v):
                bits=v['fieldBits']
                keys={}
                for side in ['initiator','responder']:
                    jwk=dict(kty='EC',crv=v['curve'],**{k:b64(bytes.fromhex(value)) for k,value in v[side].items()})
                    private=import_key(v['curve']+'/'+side+'/private','ECDH',format='jwk',jwk=jwk,usages=48,curve=bits)
                    public=import_key(v['curve']+'/'+side+'/public','ECDH',format='raw',data=b'\x04'+bytes.fromhex(v[side]['x']+v[side]['y']),usages=0,curve=bits)
                    keys[side]=(public,private)
                expected=bytes.fromhex(v['sharedSecretHex'])
                for side,other in [('initiator','responder'),('responder','initiator')]:
                    result=success(v['curve']+'/RFC5903/'+side,'ECDH','derive',key=keys[side][1],peer=keys[other][0],parameter=-1)
                    check(bytes.fromhex(result['output'])==expected,result['label'],'published shared secret including leading zeros')
                for length in [0,8,128,len(expected)*8,1,7,9,bits]:
                    result=success(v['curve']+'/length/'+str(length),'ECDH','derive',key=keys['initiator'][1],peer=keys['responder'][0],parameter=length)
                    truncated=bytearray(expected[:(length+7)//8])
                    if length%8: truncated[-1]&=0xff<<(8-length%8)
                    check(bytes.fromhex(result['output'])==bytes(truncated),result['label'],'first length bits; unused low bits zero (dated ED24.4.2)')
                result=success(v['curve']+'/derive-import-AES','ECDH','derive-import',key=keys['initiator'][1],peer=keys['responder'][0],parameter=128)
                check(bytes.fromhex(result['output'])==expected[:16],result['label'],'backend deriveBits/import/export composition')
                error(v['curve']+'/uint32-max-length','ECDH','derive',key=keys['initiator'][1],peer=keys['responder'][0],parameter=0xffffffff,expected='OperationError')
                if bits==521:
                    canonical=b'\x04'+bytes.fromhex(v['initiator']['x']+v['initiator']['y'])
                    spki=success(v['curve']+'/canonical-spki','ECDH','export',key=keys['initiator'][0],format='spki')
                    spki=bytes.fromhex(spki['output'])
                    assert spki.count(canonical)==1
                    for coordinate in ['x','y']:
                        point=dict(v['initiator'])
                        point[coordinate]=(int(point[coordinate],16)+(2**521-1)).to_bytes(66,'big').hex()
                        raw=b'\x04'+bytes.fromhex(point['x']+point['y'])
                        jwk=dict(kty='EC',crv=v['curve'],x=b64(bytes.fromhex(point['x'])),y=b64(bytes.fromhex(point['y'])))
                        for form,data,jwk_value in [('raw',raw,None),('jwk',b'',jwk),('spki',spki.replace(canonical,raw),None)]:
                            error(v['curve']+'/'+coordinate+'-plus-prime/'+form,'ECDH','import',format=form,data=data,jwk=jwk_value,usages=0,curve=bits)
                error(v['curve']+'/overlength','ECDH','derive',key=keys['initiator'][1],peer=keys['responder'][0],parameter=len(expected)*8+8,expected='OperationError')
                other=peers[384 if bits==256 else 256]
                error(v['curve']+'/wrong-curve','ECDH','derive',key=keys['initiator'][1],peer=other[0],parameter=-1,expected='InvalidAccessError')
            group(v['curve']+'/published-ECDH',published_ecdh)
        backend.check_script_guard()
        return dict(result='FAIL' if failures else 'PASS',failures=failures,records=backend.records,
                    scope='Actual CryptoAlgorithm backend methods; typed normalization/error precedence not claimed',
                    fixtureHashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [jws_path,ecdh_path]},
                    full143Closed=False,deriveKeyScope='deriveBits/AES import/export composition, not public normalization')
    finally: backend.close()

if __name__=='__main__':
    if sys.platform=='linux': C.CDLL(None).prctl(4,0)
    parser=argparse.ArgumentParser()
    parser.add_argument('--native-directory')
    parser.add_argument('--bridge-library')
    parser.add_argument('--jws-fixture',type=Path,default=Path(__file__).resolve().parents[1]/'fixtures/crypto-jws-rfc7515-signatures.json')
    parser.add_argument('--ecdh-fixture',type=Path,default=Path(__file__).resolve().parents[1]/'fixtures/crypto-ecdh-rfc5903.json')
    parser.add_argument('--report',type=Path)
    parser.add_argument('--validate-fixture',action='store_true')
    args=parser.parse_args()
    if args.validate_fixture:
        validate_fixture(args.ecdh_fixture)
        print('RFC5903 structural validation PASS:3curves/8published fields/leading zeros')
    else:
        assert args.native_directory and args.report
        try: report=verify(args.native_directory,args.jws_fixture,args.ecdh_fixture,args.bridge_library)
        except Exception as error:
            traceback.print_exc()
            report=dict(result='FAIL',infrastructureFailure=repr(error))
        args.report.write_text(json.dumps(report,indent=2)+'\n')
        print('ASYMMETRIC_BACKEND',report['result'],'operations='+str(len(report.get('records',[]))),'failures='+str(len(report.get('failures',[]))))
        assert report['result']=='PASS','Native asymmetric qualification failed; see full report'
