"""Qualify native CryptoAlgorithm backends; public WebCrypto normalization is separate."""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0,str(Path(__file__).resolve().parent))
from form_collections import Native, Case, P, I


class Bytes(C.Structure):
    _fields_ = [('data',P),('length',I)]


class Request(C.Structure):
    _fields_ = [('size',I),('algorithm',I),('operation',I),('parameter',I),('hash',I),
                ('lengthBits',I),('iterations',C.c_uint32),('extractable',I),('saltPresent',I)]
    _fields_ += [(name,Bytes) for name in ['key','iv','additionalData','input','salt','info']]


class Result(C.Structure):
    _fields_ = [('size',I),('exceptionCode',I),('exceptionName',C.c_char_p),('ownerThread',I),
                ('callbackDuringStart',I),('backendCallbackInline',I),('borrowedKeyRetains',I),
                ('keyBits',I),('extractable',I),('usages',C.c_uint32),('terminalCount',I),('output',Bytes)]


CALLBACK = C.CFUNCTYPE(None,P,C.POINTER(Result))
ALGORITHMS = {'CBC':1,'CTR':2,'GCM':3,'KW':4,'HKDF':5,'PBKDF2':6}
OPERATIONS = {'export':1,'encrypt':2,'decrypt':3,'wrap':4,'unwrap':5,'derive':6,
              'derive-import':7,'generate':8,'info':9,'cbc-raw-encrypt':10,'cbc-raw-decrypt':11}
HASHES = {'SHA-1':1,'SHA-256':256,'SHA-384':384,'SHA-512':512}


class Backend:
    def __init__(self,directory):
        self.n = Native(directory)
        self.start = self.n.bind('ranvier_test_symmetric_start',P,[P,P,CALLBACK,P])
        self.barrier = self.n.bind('ranvier_test_symmetric_barrier',I,[P])
        self.release = self.n.bind('ranvier_test_symmetric_release',I,[P])
        self.input_echo = self.n.bind('ranvier_test_symmetric_input',I,[P,I,C.POINTER(Bytes)])
        assert self.n.bind('ranvier_test_symmetric_request_size',I,[])() == C.sizeof(Request)
        assert self.n.bind('ranvier_test_symmetric_result_size',I,[])() == C.sizeof(Result)
        self.page = Case(self.n,'<p>script-free backend qualification</p>')
        assert self.n.call('rv_host_scripts_enabled',[P],self.page.host) == 0
        assert self.n.call('rv_host_vm_entry_disallowed',[P],self.page.host) == 1
        self.records = []
        self.callbacks = []

    def pump(self):
        self.n.ok('rv_host_update',[P],self.page.host)
        assert self.n.call('rv_run_loop_cycle',[I],1) >= 0

    def run(self,label,algorithm,operation,*,key=b'',iv=b'',aad=b'',data=b'',salt=b'',info=b'',
            hash='SHA-256',length=0,parameter=128,iterations=1,extractable=True,salt_present=True):
        request = Request()
        request.size,request.algorithm,request.operation = C.sizeof(Request),ALGORITHMS[algorithm],OPERATIONS[operation]
        request.hash,request.lengthBits,request.parameter = HASHES[hash],length,parameter
        request.iterations,request.extractable,request.saltPresent = iterations,extractable,salt_present
        buffers = []
        actual_inputs = [('key',key),('iv',iv),('additionalData',aad),('input',data),('salt',salt),('info',info)]
        for field,value in actual_inputs:
            buffer = C.create_string_buffer(value)
            buffers.append(buffer)
            setattr(request,field,Bytes(C.cast(buffer,P),len(value)))
        events,errors = [],[]

        def completed(_,pointer):
            try:
                value = pointer.contents
                assert value.size == C.sizeof(Result)
                assert value.output.length >= 0
                events.append(dict(exception=value.exceptionName.decode() if value.exceptionName else None,
                    exceptionCode=value.exceptionCode,ownerThread=bool(value.ownerThread),
                    callbackDuringStart=bool(value.callbackDuringStart),backendCallbackInline=bool(value.backendCallbackInline),
                    borrowedKeyRetains=value.borrowedKeyRetains,keyBits=value.keyBits,extractable=bool(value.extractable),
                    usages=value.usages,terminalCount=value.terminalCount,
                    output=C.string_at(value.output.data,value.output.length).hex()))
            except Exception as error:
                errors.append(repr(error))

        callback = CALLBACK(completed)
        self.callbacks.append(callback)
        handle = self.start(self.page.document,C.byref(request),callback,None)
        assert handle, 'private fixture rejected valid request: '+label
        for buffer in buffers:
            C.memset(buffer,0xee,C.sizeof(buffer))
        try:
            copied_inputs = {}
            for field,(name,expected) in enumerate(actual_inputs):
                echoed = Bytes()
                assert self.input_echo(handle,field,C.byref(echoed)) == 0
                copied = C.string_at(echoed.data,echoed.length)
                assert copied == expected, label+': native copied input differs: '+name
                copied_inputs[name] = dict(hex=copied.hex(),sha256=hashlib.sha256(copied).hexdigest())
            deadline = time.monotonic()+120
            while not events and not errors and time.monotonic()<deadline:
                self.pump()
            assert not errors and events, (label,events,errors)
            assert self.barrier(handle) == 0
            for _ in range(5):
                self.pump()
            assert len(events) == 1 and events[0]['terminalCount'] == 1, (label,events)
            assert events[0]['ownerThread'], label+': callback owner thread'
            result = dict(label=label,algorithm=algorithm,operation=operation,copiedInputs=copied_inputs,**events[0])
            self.records.append(result)
            return result
        finally:
            assert self.barrier(handle) == 0
            for _ in range(3):
                self.pump()
            assert self.release(handle) == 0, label+': pending fixture release'

    def close(self):
        self.page.close()


def verify(directory,fixtures):
    backend = Backend(directory)
    try:
        inputs = {}
        failures = []

        def check(condition,result,reason):
            if not condition:
                failures.append(dict(label=result['label'],reason=reason,result=result))

        def load(name):
            path = fixtures/name
            raw = path.read_bytes()
            inputs[name] = hashlib.sha256(raw).hexdigest()
            return json.loads(raw)

        def answer(result,expected):
            check(result['exception'] is None,result,'unexpected backend exception')
            check(bytes.fromhex(result['output']) == expected,result,'published answer mismatch')
            check(result['borrowedKeyRetains'] >= 1,result,'borrowed import key was not retained')

        def failure(result,name='OperationError'):
            check(result['exception'] == name and result['output'] == '',result,'backend exception mismatch: '+name)

        block = load('crypto-aes-cbc-ctr-sp800-38a.json')
        message = bytes.fromhex(''.join(block['message_blocks_hex']))
        keys = {}
        for vector in block['vectors']:
            algorithm = vector['mode']
            key = bytes.fromhex(vector['key_hex'])
            keys[vector['key_bits']] = key
            iv = bytes.fromhex(vector.get('iv_hex',vector.get('initial_counter_hex')))
            cipher = bytes.fromhex(''.join(vector['ciphertext_blocks_hex']))
            label = vector['example_id']
            if algorithm == 'CBC':
                answer(backend.run(label+'/raw-encrypt','CBC','cbc-raw-encrypt',key=key,iv=iv,data=message),cipher)
                answer(backend.run(label+'/raw-decrypt','CBC','cbc-raw-decrypt',key=key,iv=iv,data=cipher),message)
                padded = backend.run(label+'/async-padded-encrypt','CBC','encrypt',key=key,iv=iv,data=message)
                check(padded['exception'] is None and bytes.fromhex(padded['output'])[:64] == cipher,padded,'published CBC prefix mismatch')
                check(len(bytes.fromhex(padded['output'])) == 80,padded,'CBC padded length mismatch')
                answer(backend.run(label+'/async-padded-roundtrip','CBC','decrypt',key=key,iv=iv,
                                   data=bytes.fromhex(padded['output'])),message)
            else:
                for operation,data,expected in [('encrypt',message,cipher),('decrypt',cipher,message)]:
                    answer(backend.run(label+'/'+operation,'CTR',operation,key=key,iv=iv,data=data,
                                       parameter=vector['counter_field_bits']),expected)

        for algorithm in ['CBC','CTR','GCM','KW']:
            for bits,key in sorted(keys.items()):
                exported = backend.run(f'{algorithm}/{bits}/import-export',algorithm,'export',key=key)
                answer(exported,key)
                check(exported['keyBits'] == bits and exported['extractable'],exported,'AES imported key metadata')
                generated = backend.run(f'{algorithm}/{bits}/generate-export',algorithm,'generate',length=bits)
                check(generated['exception'] is None and generated['keyBits'] == bits,generated,'AES generated key metadata')
                check(len(bytes.fromhex(generated['output'])) == bits//8 and generated['extractable'],generated,'AES generated key export')

        gcm = load('crypto-aes-gcm-cavp.json')
        for index,vector in enumerate(gcm['vectors']):
            values,expected = vector['input'],vector['expected']
            arguments = dict(key=bytes.fromhex(values['Key']),iv=bytes.fromhex(values['IV']),
                             aad=bytes.fromhex(values.get('AAD','')),parameter=vector['source']['group']['Taglen'])
            label = f'GCM/CAVP/{index}/{vector["operation"]}'
            if vector['operation'] == 'encrypt':
                ciphertext = bytes.fromhex(expected['CT']+expected['Tag'])
                answer(backend.run(label,'GCM','encrypt',data=bytes.fromhex(values['PT']),**arguments),ciphertext)
                answer(backend.run(label+'/decrypt','GCM','decrypt',data=ciphertext,**arguments),bytes.fromhex(values['PT']))
            else:
                result = backend.run(label,'GCM','decrypt',data=bytes.fromhex(values['CT']+values['Tag']),**arguments)
                if expected.get('result') == 'FAIL':
                    failure(result)
                else:
                    answer(result,bytes.fromhex(expected['PT']))

        kw = load('crypto-aes-kw-rfc3394.json')
        for vector in kw['vectors']:
            key,plain,cipher = [bytes.fromhex(vector[field]) for field in ['kek_hex','key_data_hex','ciphertext_hex']]
            label = 'KW/RFC3394/'+vector['case']
            answer(backend.run(label+'/wrap','KW','wrap',key=key,data=plain),cipher)
            answer(backend.run(label+'/unwrap','KW','unwrap',key=key,data=cipher),plain)
            corrupt = bytes([cipher[0]^1])+cipher[1:]
            failure(backend.run(label+'/integrity','KW','unwrap',key=key,data=corrupt))

        hkdf = load('crypto-hkdf-rfc5869.json')
        derived_hashes = set()
        for vector in hkdf['vectors']:
            arguments = dict(key=bytes.fromhex(vector['ikm_hex']),salt=bytes.fromhex(vector['salt_hex'] or ''),
                salt_present=vector['salt_hex'] is not None,info=bytes.fromhex(vector['info_hex']),
                hash=vector['hash'],extractable=False)
            expected = bytes.fromhex(vector['okm_hex'])
            label = 'HKDF/RFC5869/'+vector['case']
            answer(backend.run(label,'HKDF','derive',length=vector['l_octets']*8,**arguments),expected)
            if vector['hash'] not in derived_hashes:
                answer(backend.run(label+'/derive-import-export','HKDF','derive-import',length=128,**arguments),expected[:16])
                derived_hashes.add(vector['hash'])

        pbkdf = load('crypto-pbkdf2-rfc6070.json')
        for index,vector in enumerate(pbkdf['vectors']):
            arguments = dict(key=bytes.fromhex(vector['password_hex']),salt=bytes.fromhex(vector['salt_hex']),
                             iterations=vector['iterations'],hash='SHA-1',extractable=False)
            expected = bytes.fromhex(vector['derived_key_hex'])
            label = 'PBKDF2/RFC6070/'+str(vector['case'])
            answer(backend.run(label,'PBKDF2','derive',length=vector['dk_len_octets']*8,**arguments),expected)
            if index == 0:
                answer(backend.run(label+'/derive-import-export','PBKDF2','derive-import',length=128,**arguments),expected[:16])

        key,iv = keys[128],bytes(range(16))
        failure(backend.run('CBC/bad-IV','CBC','encrypt',key=key,iv=iv[:-1],data=message))
        published = next(v for v in block['vectors'] if v['mode']=='CBC' and v['key_bits']==128)
        failure(backend.run('CBC/raw-vector-is-not-valid-PKCS7','CBC','decrypt',key=key,iv=iv,
                            data=bytes.fromhex(''.join(published['ciphertext_blocks_hex']))))
        first_cipher = bytes.fromhex(published['ciphertext_blocks_hex'][0])
        failure(backend.run('CBC/padding-greater-than-block','CBC','decrypt',key=key,iv=iv,data=first_cipher))
        for last in [0,2]:
            changed_iv = iv[:-1]+bytes([iv[-1]^message[15]^last])
            failure(backend.run('CBC/invalid-padding-last-byte/'+str(last),'CBC','decrypt',key=key,
                                iv=changed_iv,data=first_cipher))
        for padding in [1,2]:
            changed_iv = bytearray(iv)
            for at in range(16-padding,16):
                changed_iv[at] ^= message[at]^padding
            answer(backend.run('CBC/valid-padding/'+str(padding),'CBC','decrypt',key=key,
                               iv=bytes(changed_iv),data=first_cipher),message[:16-padding])
        for bits in [0,129]:
            failure(backend.run('CTR/invalid-counter-length/'+str(bits),'CTR','encrypt',key=key,iv=iv,data=b'abc',parameter=bits))
        failure(backend.run('CTR/counter-space-exhausted','CTR','encrypt',key=key,iv=iv,data=bytes(48),parameter=1))
        failure(backend.run('GCM/invalid-tag-length','GCM','encrypt',key=key,iv=bytes(12),data=b'abc',parameter=31))
        failure(backend.run('GCM/empty-IV','GCM','encrypt',key=key,iv=b'',data=b'abc'))
        failure(backend.run('KW/invalid-block-length','KW','wrap',key=key,data=b'1234567'))
        for algorithm in ['HKDF','PBKDF2']:
            failure(backend.run(algorithm+'/nonbyte-length',algorithm,'derive',key=b'password',salt=b'salt',
                                hash='SHA-256',length=7,extractable=False))
            failure(backend.run(algorithm+'/extractable-base-key',algorithm,'info',key=b'password',
                                extractable=True),'SyntaxError')
        failure(backend.run('HKDF/expand-limit','HKDF','derive',key=b'password',salt=b'salt',
                            length=(255*32+1)*8,hash='SHA-256',extractable=False))
        failure(backend.run('PBKDF2/zero-iterations','PBKDF2','derive',key=b'password',salt=b'salt',
                            length=128,iterations=0,hash='SHA-256',extractable=False))
        assert backend.n.call('rv_host_scripts_enabled',[P],backend.page.host) == 0
        assert backend.n.call('rv_host_vm_entry_disallowed',[P],backend.page.host) == 1
        return dict(result='FAIL' if failures else 'PASS',failures=failures,
            scope='Direct CryptoAlgorithm backend methods; public typed normalization and error ordering are separate',
            fixtureSource='30fd88d7d618a03f478f0a090305c7be2f20472e',fixtureHashes=inputs,records=backend.records,
            vectorCounts=dict(cbcCtr=len(block['vectors']),gcm=len(gcm['vectors']),kw=len(kw['vectors']),
                              hkdf=len(hkdf['vectors']),pbkdf2=len(pbkdf['vectors'])),
            full143Closed=False,deriveKeyScope='Actual getKeyLength/deriveBits/AES import/export composition only')
    finally:
        backend.close()


if __name__ == '__main__':
    if sys.platform == 'linux':
        C.CDLL(None).prctl(4,0)
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory',required=True)
    parser.add_argument('--fixtures',type=Path,default=Path(__file__).resolve().parents[1]/'fixtures')
    parser.add_argument('--report',type=Path,required=True)
    args = parser.parse_args()
    try:
        report = verify(args.native_directory,args.fixtures)
    except Exception as error:
        traceback.print_exc()
        report = dict(result='FAIL',infrastructureFailure=repr(error))
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    assert report['result'] == 'PASS', 'Symmetric backend qualification failed; see report'
