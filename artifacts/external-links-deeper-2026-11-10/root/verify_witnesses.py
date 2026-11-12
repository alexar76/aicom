"""Offline Ed25519 verification from saved first-party witness publications."""
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT=Path(__file__).resolve().parent

def main():
    issuer=json.loads((ROOT/'histor-issuer.raw').read_text())
    machine=json.loads((ROOT/'crawlcheck-witness-machine.raw').read_text())
    assert issuer['checkpoint']['vkey'] in (ROOT/'official-staging-source.raw').read_text()
    markovian=(ROOT/'markovian-about.raw').read_text()
    key_match=re.search(r'markovianprotocol\.com/witness\+[0-9a-f]{8}\+[A-Za-z0-9+/=]+',markovian)
    assert key_match
    vkeys=[issuer['checkpoint']['vkey'],machine['vkey'],key_match.group(0)]
    keys={}
    for value in vkeys:
        name,identifier,encoded=value.split('+',2)
        raw=base64.b64decode(encoded,validate=True)
        computed=hashlib.sha256(name.encode()+b'\n'+raw).digest()[:4]
        assert computed.hex()==identifier
        keys[(name,computed)]=(raw[0],Ed25519PublicKey.from_public_bytes(raw[1:]))
    checkpoints=(ROOT/'markovian-checkpoints.raw').read_text()
    match=re.search(r'== histor\.modelmarket\.dev/log[^\n]*\n(.*?)(?=\n== |\Z)',checkpoints,re.S)
    assert match
    (ROOT/'markovian-histor-checkpoint.txt').write_text(match.group(1).strip()+'\n')
    results=[]
    for file in ['histor-checkpoint.raw','crawlcheck-histor-checkpoint.raw','markovian-histor-checkpoint.txt']:
        data=(ROOT/file).read_text();body,lines=data.split('\n\n',1);body+='\n'
        item={'file':file,'origin':body.splitlines()[0],'tree_size':int(body.splitlines()[1]),'root_base64':body.splitlines()[2],'signatures':[]}
        for line in lines.strip().splitlines():
            assert line.startswith('— ')
            name,encoded=line[2:].rsplit(' ',1);raw=base64.b64decode(encoded,validate=True)
            kind,pub=keys[(name,raw[:4])]
            message=body.encode();signature=raw[4:]
            record={'name':name,'type':kind}
            if kind==4:
                timestamp=struct.unpack('>Q',signature[:8])[0]
                message=f'cosignature/v1\ntime {timestamp}\n'.encode()+message
                signature=signature[8:]
                record['cosignature_time_utc']=datetime.fromtimestamp(timestamp,timezone.utc).isoformat()
            pub.verify(signature,message)
            record['signature_valid']=True
            try:
                pub.verify(signature,message+b'x')
            except InvalidSignature:
                record['negative_control_rejected']=True
            else: raise AssertionError('tampered message accepted')
            item['signatures'].append(record)
        results.append(item)
    assert results[1]['tree_size']==results[2]['tree_size']
    assert results[1]['root_base64']==results[2]['root_base64']
    summary={'checkpoints':results,'same_head_on_two_external_witnesses':True,'key_sources':['histor-issuer.raw','crawlcheck-witness-machine.raw','markovian-about.raw'],'freshness_limit':'Timestamps are signed claims of the witness, not independently validated wall clocks. No new checkpoint was submitted by this audit.'}
    (ROOT/'checkpoint-verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
