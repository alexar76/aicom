"""Run real crash/restart tests in an isolated candidate Hub container."""

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import textwrap


SETUP = """
import os
from aimarket_hub import channels, credits
from aimarket_hub.database import HubDatabase

db = HubDatabase(os.environ['AIMARKET_DB_PATH'])
ledger = credits.CreditsLedger(db._conn)
seller = ledger.create_account()['account_id']
channel = channels._ledger.open(0.01, wallet='synthetic-custody-smoke')['channel']
receipt_id = 'publisher-outbox-crash-smoke'
assert channels._ledger.hold(channel['channel_id'], 0.01, receipt_id, secret=channel['channel_secret'])['ok']
share = credits.PublisherShare(seller, 0.007, receipt_id, 'synthetic crash smoke')
assert channels._ledger.capture_hold(receipt_id, publisher_share=share)['ok']
pay = ledger.pay_publisher

def hard_exit(*args, **kwargs):
    if os.environ['CUSTODY_CRASH_WINDOW'] == 'after-credit-commit':
        assert pay(*args, **kwargs)['paid_usd'] == 0.007
    os._exit(43)

ledger.pay_publisher = hard_exit
channels._ledger.reconcile_publisher_shares(ledger, receipt_id=receipt_id)
raise AssertionError('expected hard exit')
"""

RECOVER = """
import os
from aimarket_hub import channels, credits
from aimarket_hub.api import create_app
from aimarket_hub.config import HubConfig
from aimarket_hub.database import HubDatabase
from fastapi.testclient import TestClient

config = HubConfig()
config.db_path = os.environ['AIMARKET_DB_PATH']
db = HubDatabase(config.db_path)
app = create_app(config=config, db=db)
with TestClient(app) as client:
    assert client.get('/ai-market/v2/health').status_code == 200
    assert channels._ledger.reconcile_publisher_shares(credits.CreditsLedger(db._conn),
                                                       receipt_id='publisher-outbox-crash-smoke') == 0
"""


def state(paths):
    with sqlite3.connect(paths['AIMARKET_CHANNELS_DB_PATH']) as channel, sqlite3.connect(paths['AIMARKET_DB_PATH']) as credit:
        pending = channel.execute('SELECT amount_mc, credited_at, cash_backed FROM channel_publisher_shares').fetchall()
        debits = channel.execute('SELECT amount_cents FROM debited_receipts').fetchall()
        rows = credit.execute("SELECT amount_mc FROM credit_ledger WHERE kind = 'payout'").fetchall()
        balances = credit.execute('SELECT balance_mc FROM credit_accounts').fetchall()
        assert len(pending) == len(debits) == len(balances) == 1
        assert pending[0][2] == 0
        return {'obligation_millicents': pending[0][0], 'obligation_acknowledged': bool(pending[0][1]),
                'debit_cents': debits[0][0], 'publisher_payout_count': len(rows),
                'publisher_balance_millicents': balances[0][0]}


results = []
for window in ('before-credit-commit', 'after-credit-commit'):
    with tempfile.TemporaryDirectory(prefix='publisher-outbox-crash-') as directory:
        root = Path(directory)
        env = {name: value for name, value in os.environ.items()
               if not name.startswith(('AIMARKET_', 'AIFACTORY_', 'HUB_', 'PG')) and 'DATABASE' not in name}
        env.update({'PYTHONPATH': '/app', 'CUSTODY_CRASH_WINDOW': window,
                    'AIMARKET_ALLOW_DEMO_CREDIT': '1', 'AIMARKET_ESCROW_REQUIRED': '0',
                    'AIMARKET_CREDITS_ENABLED': '1', 'AIMARKET_SKIP_SEED': '1', 'AIMARKET_AUTO_CRAWL': '0',
                    'AIMARKET_FEDERATION_ASSAY': '0', 'AIMARKET_TOPUP_ENABLED': '0',
                    'AIMARKET_HUB_URL': 'https://custody-smoke.invalid',
                    'AIMARKET_SIGNING_KEY_PATH': str(root / 'smoke.key'),
                    'AIMARKET_DEPOSIT_CLAIMS_DIR': str(root / 'deposit-claims'),
                    'AIMARKET_CHANNELS_DB_PATH': str(root / 'channels.db'),
                    'AIMARKET_DB_PATH': str(root / 'hub.db')})
        child = subprocess.run([sys.executable, '-c', textwrap.dedent(SETUP)], env=env, timeout=30)
        assert child.returncode == 43, child.returncode
        interrupted = state(env)
        committed = window == 'after-credit-commit'
        assert interrupted == {'obligation_millicents': 700, 'obligation_acknowledged': False, 'debit_cents': 1,
                               'publisher_payout_count': int(committed),
                               'publisher_balance_millicents': 700 if committed else 0}, interrupted
        subprocess.run([sys.executable, '-c', textwrap.dedent(RECOVER)], env=env, timeout=30, check=True)
        recovered = state(env)
        assert recovered == {'obligation_millicents': 700, 'obligation_acknowledged': True, 'debit_cents': 1,
                             'publisher_payout_count': 1, 'publisher_balance_millicents': 700}, recovered
        results.append({'crash_window': window, 'forced_exit_code': child.returncode,
                        'after_crash': interrupted, 'after_app_start_and_replay': recovered})
print(json.dumps({'production_image': os.environ.get('CUSTODY_IMAGE'), 'scenarios': results, 'network': 'none', 'production_volume_mounts': False,
                  'storage': 'disposable SQLite', 'funds': 'synthetic'}, indent=2))
