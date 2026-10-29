"""Linux-only offline tests; all transport and credentials are synthetic."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import threading
import unittest
import uuid

import host_relay as relay
from test_host_relay import FakeTransport, FakeResponse, valid_request


class DollarBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)/'queue'
        self.transport = FakeTransport()
        self.api = relay.Relay(self.root, 'synthetic-budget-key', 'deepseek-flash',
                               opener=self.transport, budget_nanousd=relay.RESERVATION_NANOUSD)

    def tearDown(self):
        self.api.close()
        self.temp.cleanup()

    def request(self):
        path = self.root/'req'/(uuid.uuid4().hex+'.json')
        path.write_text(json.dumps(valid_request()))
        return path

    def test_prices_are_conservative_integer_peak_rates(self):
        self.assertEqual(relay.usage_upper_nanousd({'prompt_tokens':100,'completion_tokens':10,'prompt_cache_hit_tokens':40}),60*300+40*6+10*1200)
        for usage in [{'prompt_tokens':True,'completion_tokens':1}, {'prompt_tokens':1,'completion_tokens':701},
                      {'prompt_tokens':1,'completion_tokens':1,'prompt_cache_hit_tokens':2}]:
            with self.assertRaises(relay.RelayError):relay.usage_upper_nanousd(usage)

    def test_settlement_and_restart_do_not_reset_spend(self):
        self.api.process(self.request())
        charged=self.api.held_nanousd
        self.assertEqual(charged,20*300+10*1200)
        self.api.close()
        self.api=relay.Relay(self.root,'synthetic-budget-key','deepseek-flash',opener=self.transport,
                             budget_nanousd=relay.RESERVATION_NANOUSD)
        self.assertEqual(self.api.held_nanousd,charged)
        # With a one-reservation budget, even the next small reservation no longer fits.
        result=self.api.process(self.request())
        self.assertEqual(result['error']['code'],'dollar_budget_exhausted')
        self.assertEqual(len(self.transport.requests),1)

    def test_uncertain_transport_keeps_the_full_reservation(self):
        self.api.opener=FakeTransport(error=TimeoutError())
        self.assertEqual(self.api.process(self.request())['status'],'error')
        self.assertEqual(self.api.held_nanousd,relay.RESERVATION_NANOUSD)
        self.assertEqual(self.api.process(self.request())['error']['code'],'dollar_budget_exhausted')

    def test_concurrent_dispatch_cannot_overbook_a_reservation(self):
        entered=threading.Event(); release=threading.Event()
        def transport(_request,timeout):
            entered.set()
            self.assertTrue(release.wait(5))
            return FakeResponse()
        self.api.opener=transport
        first=self.request();second=self.request()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(self.api.process,first)
            self.assertTrue(entered.wait(5))
            self.assertEqual(self.api.process(second)['error']['code'],'dollar_budget_exhausted')
            release.set()
            self.assertEqual(future.result()['status'],'ok')

    def test_restart_cannot_increase_the_money_limit(self):
        self.api.close()
        with self.assertRaises(relay.RelayError):
            relay.Relay(self.root,'synthetic-budget-key','deepseek-flash',budget_nanousd=relay.RESERVATION_NANOUSD+1)

    def test_invalid_usage_is_unknown_cost_and_not_refunded(self):
        payload={'id':'synthetic','model':'deepseek-flash','choices':[{'message':{'content':'{}'}}],
                 'usage':{'prompt_tokens':-1,'completion_tokens':10}}
        self.api.opener=FakeTransport(payload=payload)
        self.assertEqual(self.api.process(self.request())['status'],'error')
        self.assertEqual(self.api.held_nanousd,relay.RESERVATION_NANOUSD)


if __name__=='__main__':unittest.main()
