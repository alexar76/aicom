"""Verify the archived Chrome DevTools tool sets, labels and inclusion proofs offline."""
from copy import deepcopy
import json
from pathlib import Path

from awr import canonical_sri, canonicalize, parse_did_key
from awr.proof import verify_document_signature
from histor import merkle
from histor.logbook import STH_TYPE, verify_document
from histor.subject import tool_set_digest

ROOT = Path(__file__).resolve().parent
ISSUER = 'did:key:z6Mkw1CVxsPj9utYp7VXWEbuuGM9Ev47itwKu1UfKd5ByxR9'


def load(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def main():
    change = load('change.json')
    publisher = load('issuer.json')
    before = load('label.before.json')
    after = load('label.json')
    key = parse_did_key(ISSUER)
    assert publisher['did'] == ISSUER and publisher['publicKeyHex'] == key.hex()
    prior = after['credentialSubject']['mcpTrustLabel']['priorLabel']
    assert prior['id'] == before['id'] and prior['digestSRI'] == canonical_sri(before)
    assert after['id'] == change['label_id']
    heads = []
    for side, prefix, label, proof_name in (
        ('before', 'from', before, 'proof.before.json'),
        ('after', 'to', after, 'proof.json'),
    ):
        tools = load(f'observed.{side}.json')
        digest, _ = tool_set_digest(tools)
        subject = label['credentialSubject']
        record = subject['mcpTrustLabel']
        assert record['server']['name'] == change['name']
        assert record['toolSet'] == {'count': len(tools), 'digestSRI': digest}
        assert digest == change[f'{prefix}_toolset']
        assert subject['verifiedWork']['digestSRI'] == change[f'{prefix}_subject']
        assert label['issuer']['id'] == ISSUER and verify_document_signature(label, label['proof'], key)
        tampered = deepcopy(label)
        tampered['credentialSubject']['mcpTrustLabel']['toolSet']['count'] += 1
        assert not verify_document_signature(tampered, label['proof'], key)

        proof = load(proof_name)
        head = proof['sth']
        assert proof['labelId'] == label['id']
        assert head['log'] == ISSUER and verify_document(head, ISSUER, STH_TYPE)
        path = [bytes.fromhex(x) for x in proof['inclusionProof']]
        root = bytes.fromhex(head['rootHash'])
        assert merkle.verify_inclusion(merkle.leaf_hash(canonicalize(label)), proof['leafIndex'], head['treeSize'], path, root)
        assert not merkle.verify_inclusion(merkle.leaf_hash(canonicalize(tampered)), proof['leafIndex'], head['treeSize'], path, root)
        heads.append(head)
        print(f"PASS {side} digest, label signature, leaf {proof['leafIndex']}, modified label rejected")
    assert heads[0] == heads[1]
    print(f"PASS signed tree head {heads[0]['treeSize']} and continuity label links both observations")


if __name__ == '__main__':
    main()
