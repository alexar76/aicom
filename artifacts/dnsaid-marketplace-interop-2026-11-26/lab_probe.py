"""Repeat the marketplace pointer check on the Instruqt lab workstation."""

import asyncio
import json
import struct
import sys
from urllib.parse import urlsplit
from urllib.request import urlopen


ZONE = 'builder.test'
TARGET = 'modelmarket.dev'
SUFFIX = b'agent-marketplace'
CASES = {'len': struct.pack('!H', len(SUFFIX)) + SUFFIX, 'plain': SUFFIX}


def domain(case):
    return f'mmwk1126-{case}.{ZONE}'


def publish():
    import dns.name
    import dns.query
    import dns.rdata
    import dns.rcode
    import dns.update
    from dns_aid.core.publisher import get_default_backend

    backend = get_default_backend()
    assert type(backend).__name__ == 'DDNSBackend'
    update = dns.update.Update(ZONE, keyring=backend._keyring, keyalgorithm=backend._algorithm)
    for case, value in CASES.items():
        owner = '_index._agents.' + domain(case) + '.'
        wire = struct.pack('!H', 1) + dns.name.from_text(TARGET + '.').to_wire()
        wire += struct.pack('!HH', 1, 3) + b'\x02h2'
        wire += struct.pack('!HH', 65409, len(value)) + value
        rdata = dns.rdata.from_wire('IN', 'SVCB', wire, 0, len(wire))
        update.absent(owner, 'SVCB')
        update.add(owner, 60, rdata)
    response = dns.query.tcp(update, backend.server, port=backend.port, timeout=backend.timeout)
    status = dns.rcode.to_text(response.rcode())
    print('ADD', status, *(domain(case) for case in CASES))
    assert status == 'NOERROR'


def get_json(url):
    parts = urlsplit(url)
    assert parts.scheme == 'https' and parts.hostname == TARGET
    with urlopen(url, timeout=12) as response:
        assert response.geturl() == url and response.status == 200
        return json.load(response)


async def sdk_test():
    from dns_aid.core.catalog_pointer import resolve_catalog_pointer_detail

    for case in ('control', 'len', 'plain'):
        pointer = await resolve_catalog_pointer_detail(domain(case))
        if not pointer:
            print(case, 'no pointer')
            continue
        print(case, urlsplit(pointer.url).path)
        result = get_json(pointer.url)
        if 'catalogue_url' in result:
            catalogue = get_json(result['catalogue_url'])
            assert catalogue['tools']
            print('200 ->', urlsplit(result['catalogue_url']).path)
        else:
            print('200 ->', ','.join(sorted(result)))


def dawn_test():
    from dawnlab.unicast import resolve_owner

    for case in ('control', 'len', 'plain'):
        owner = '_index._agents.' + domain(case)
        result = resolve_owner(owner)
        for record in result['svcb']:
            value = ascii(record['params'].get('well-known'))
            print(case, 'AD=' + str(result['svcb_ad']), 'well-known=' + value)
        if not result['svcb']:
            print(case, 'no SVCB')


if __name__ == '__main__':
    if sys.argv[1] == 'add':
        publish()
    elif sys.argv[1] == 'sdk':
        asyncio.run(sdk_test())
    else:
        dawn_test()
