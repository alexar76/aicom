"""Failure modes of the native-fee valuation, independent of Hub behavior."""
import time
from decimal import Decimal

import pytest

from aimarket_hub.native_price import ETH_USD, SEQUENCER, native_price


def encoded(*values):
    return '0x' + ''.join(format(v % 2**256, '064x') for v in values)


class RPC:
    def __init__(self):
        now = int(time.time())
        self.block = now
        self.price = [1, 3000 * 10**8, now - 10, now - 10, 1]
        self.sequencer = [1, 0, now - 7200, now - 7200, 1]
        self.decimals = 8
        self.chain = 8453
        self.other_price = None
        self.unavailable = False
        self.malformed = False

    async def __call__(self, client, url, method, params):
        if self.unavailable:
            raise ValueError('RPC unavailable')
        if method == 'eth_chainId':
            return hex(self.chain)
        if method == 'eth_getBlockByNumber':
            return {'number': '0x1234', 'timestamp': hex(self.block)}
        assert params[1] == '0x1234'  # All reads use the observed block.
        call = params[0]
        if call['to'] == SEQUENCER:
            return encoded(*self.sequencer)
        assert call['to'] == ETH_USD
        if call['data'] == '0x313ce567':
            return encoded(self.decimals)
        if self.malformed:
            return '0x00'
        price = list(self.price)
        if url == 'https://second.test' and self.other_price:
            price[1] = self.other_price * 10**8
        return encoded(*price)


async def quote(rpc, **kwargs):
    return await native_price(None, 'https://first.test', rpc, secondary='https://second.test', **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize('price', [20, 20000, 100000])
async def test_no_fixed_price_cap(price):
    rpc = RPC()
    rpc.price[1] = price * 10**8
    result = await quote(rpc)
    assert Decimal(result['native_usd_ceiling']) == Decimal(price) * Decimal('1.25')


@pytest.mark.asyncio
async def test_manual_floor_cannot_reduce_live_price():
    rpc = RPC()
    rpc.price[1] = 20000 * 10**8
    assert Decimal((await quote(rpc, floor='6000'))['native_usd_ceiling']) == 25000
    assert Decimal((await quote(rpc, floor='30000'))['native_usd_ceiling']) == 30000


@pytest.mark.asyncio
async def test_take_higher_rpc_observation():
    rpc = RPC()
    rpc.other_price = 3030
    assert Decimal((await quote(rpc))['native_usd_ceiling']) == Decimal('3787.5')


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['zero', 'negative', 'stale', 'future', 'incomplete', 'zero_round',
    'decimals', 'chain', 'sequencer_down', 'sequencer_grace', 'sequencer_uninitialized',
    'stale_block', 'future_block', 'disagree', 'unavailable', 'malformed'])
async def test_fail_closed(failure):
    rpc = RPC()
    if failure == 'zero': rpc.price[1] = 0
    if failure == 'negative': rpc.price[1] = -1
    if failure == 'stale': rpc.price[2] = rpc.price[3] = rpc.block - 1501
    if failure == 'future': rpc.price[3] = rpc.block + 1
    if failure == 'incomplete': rpc.price[4] = 0
    if failure == 'zero_round': rpc.price[0] = 0
    if failure == 'decimals': rpc.decimals = 18
    if failure == 'chain': rpc.chain = 1
    if failure == 'sequencer_down': rpc.sequencer[1] = 1
    if failure == 'sequencer_grace': rpc.sequencer[2] = rpc.sequencer[3] = rpc.block - 3599
    if failure == 'sequencer_uninitialized': rpc.sequencer[2] = 0
    if failure == 'stale_block': rpc.block -= 121
    if failure == 'future_block': rpc.block += 60
    if failure == 'disagree': rpc.other_price = 3200
    if failure == 'unavailable': rpc.unavailable = True
    if failure == 'malformed': rpc.malformed = True
    with pytest.raises(ValueError):
        await quote(rpc, floor='6000')  # Manual value is never a fallback.


@pytest.mark.asyncio
async def test_same_rpc_does_not_count_twice():
    with pytest.raises(ValueError, match='second RPC hostname'):
        await native_price(None, 'https://first.test/a', RPC(), secondary='https://first.test/b')


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['429', '503', 'timeout'])
async def test_rpc_recovers_transient_failure_with_identical_request(failure, monkeypatch):
    import httpx
    from aimarket_hub.pipeline_client import _rpc
    seen, delays = [], []
    async def sleep(seconds): delays.append(seconds)
    monkeypatch.setattr('aimarket_hub.pipeline_client.asyncio.sleep', sleep)
    def respond(request):
        seen.append(request.content)
        if len(seen) < 3:
            if failure == 'timeout': raise httpx.ReadTimeout('temporary')
            return httpx.Response(int(failure), headers={'Retry-After': '1'})
        return httpx.Response(200, json={'result': '0x2105'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as c:
        assert await _rpc(c, 'https://rpc.test', 'eth_chainId', []) == '0x2105'
    assert len(seen) == 3 and len(set(seen)) == 1 and len(delays) == 2


@pytest.mark.asyncio
async def test_rpc_throttle_is_bounded_and_does_not_expose_rpc_credentials(monkeypatch):
    import httpx
    from aimarket_hub.pipeline_client import _rpc
    seen, delays = [], []
    async def sleep(seconds): delays.append(seconds)
    monkeypatch.setattr('aimarket_hub.pipeline_client.asyncio.sleep', sleep)
    def respond(request):
        seen.append(request)
        return httpx.Response(429, headers={'Retry-After': '999999'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as c:
        with pytest.raises(ValueError, match='resume the saved order') as exc:
            await _rpc(c, 'https://rpc.test/private-credential', 'eth_chainId', [])
    assert len(seen) == 3 and delays == [5, 5]
    assert 'private-credential' not in str(exc.value)
