"""Verify fixed publication URLs from a remote gVisor network client."""
import hashlib
import json
from pathlib import Path
import urllib.request

base = 'https://modelmarket.dev/blog/media/warden-security-comparison-2026-11-07/'
receipt = json.loads(Path('/output/bundle-receipt.json').read_text())
expected = {
    'cover.png': '79f6538f7810c3ac2b58f9b7e9e17d20a29edfbd39be809d8d45f7096bbbd0b0',
    'method.png': '165403710e7d21583a54c98da8871b5c230776868ba1f319d4aa5d9fb0cb6818',
    'results.png': 'dfb3b3e7b6b94c3cebf911046d9ec3174ae53b1ad6629ec12e7db8dac50abc92',
    'coverage.png': '32e9fcf14fd5432981cbda3889b6ae8978508b129002700d454fb2385083d0dd',
    'reports-and-data.zip': receipt['sha256'],
}
checked = []
for name, digest in expected.items():
    request = urllib.request.Request(base + name, headers={
        'User-Agent': 'AIMarket-editorial-verification/1.0',
        'Accept-Encoding': 'identity',
    })
    with urllib.request.urlopen(request, timeout=90) as response:
        assert response.status == 200
        assert response.url == base + name
        content = response.read(64 * 1024 * 1024 + 1)
        assert len(content) <= 64 * 1024 * 1024
        actual = hashlib.sha256(content).hexdigest()
        assert actual == digest, (name, actual)
        if name.endswith('.png'):
            assert content.startswith(b'\x89PNG\r\n\x1a\n')
        else:
            assert content.startswith(b'PK\x03\x04')
            assert len(content) == receipt['bytes']
        checked.append({'url': response.url, 'status': response.status,
                        'bytes': len(content), 'sha256': actual,
                        'contentType': response.headers.get('Content-Type'),
                        'httpDate': response.headers.get('Date')})
result = {'format': 'warden.public-assets-verification/v1',
          'execution': 'remote gVisor', 'allPassed': True, 'files': checked}
Path('/output/public-assets-verification.json').write_text(
    json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
