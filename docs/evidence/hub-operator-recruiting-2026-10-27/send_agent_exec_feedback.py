"""Send the exact user-approved feedback once and preserve its receipt.

Authorized in this chat: Да, отправляй подготовленное сообщение agent-exec через feedback.
No retries, authentication, payment, redirects, or other remote writes.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import urllib.error
import urllib.request

CAMPAIGN = Path('/Users/alex/Desktop/ai_tests/aicompany/PromoMaterials/outreach/hub-operators-2026-10-27')
PAYLOAD_PATH = CAMPAIGN / 'agent-exec-feedback.json'
RECEIPT_PATH = CAMPAIGN / 'agent-exec-feedback-receipt.json'
ATTEMPT_PATH = Path(__file__).with_name('agent-exec-send-attempt.json')
EXPECTED_SHA256 = 'fbd7816b84c9c3cec1ea3ea7d9500de318dee5bb2107f2e2d669a2a32e66df0f'
ENDPOINT = 'https://agent-exec.448c.org/feedback'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def now():
    return datetime.now(timezone.utc).isoformat()


if __name__ == '__main__':
    if RECEIPT_PATH.exists() or ATTEMPT_PATH.exists():
        raise SystemExit('A send attempt or receipt already exists; refusing a duplicate POST.')
    payload = PAYLOAD_PATH.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    if digest != EXPECTED_SHA256:
        raise SystemExit('The approved payload changed; refusing to send different content.')
    parsed = json.loads(payload)
    assert set(parsed) == {'message'}
    assert 0 < len(parsed['message']) <= 8000
    attempt = {
        'started_at_utc': now(), 'endpoint': ENDPOINT, 'method': 'POST',
        'payload_sha256': digest, 'payload_path': str(PAYLOAD_PATH),
        'authorization': 'Explicit user instruction in this chat to send the prepared message through feedback',
        'state': 'attempt_started_no_automatic_retry',
    }
    ATTEMPT_PATH.write_text(json.dumps(attempt, ensure_ascii=False, indent=2) + '\n')
    receipt = dict(attempt)
    receipt['request_body'] = parsed
    request = urllib.request.Request(
        ENDPOINT, data=payload, method='POST',
        headers={'Content-Type': 'application/json', 'Accept': 'application/json',
                 'User-Agent': 'aicom-agent-exec-feedback/1.0'},
    )
    try:
        opener = urllib.request.build_opener(NoRedirect())
        with opener.open(request, timeout=30) as response:
            raw = response.read(65536)
            receipt.update(http_status=response.status, final_url=response.url,
                           response_headers={key: response.headers.get(key) for key in
                                             ('Date', 'Content-Type', 'X-Request-Id')})
        receipt['response_body'] = json.loads(raw)
        receipt['confirmed_received'] = (
            200 <= receipt['http_status'] < 300
            and receipt['response_body'].get('received') is True
            and receipt['response_body'].get('id') is not None
        )
        receipt['state'] = 'received_by_service' if receipt['confirmed_received'] else 'needs_reconciliation'
    except urllib.error.HTTPError as error:
        receipt.update(http_status=error.code, confirmed_received=False,
                       state='http_error_no_retry',
                       response_body_text=error.read(65536).decode('utf-8', errors='replace'))
    except Exception as error:
        receipt.update(confirmed_received=False, state='unknown_outcome_no_retry', error=str(error))
    receipt['completed_at_utc'] = now()
    RECEIPT_PATH.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    attempt.update(state=receipt['state'], completed_at_utc=receipt['completed_at_utc'],
                   receipt_path=str(RECEIPT_PATH))
    ATTEMPT_PATH.write_text(json.dumps(attempt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: receipt.get(key) for key in
                      ('state', 'http_status', 'confirmed_received', 'response_body', 'error')},
                     ensure_ascii=False))
    print(str(RECEIPT_PATH))
    if not receipt['confirmed_received']:
        raise SystemExit(1)
