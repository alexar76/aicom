# Test Vectors

Reference test vectors for implementors verifying Ed25519 signature verification and manifest parsing.

## Keys

Test keypair (DO NOT USE IN PRODUCTION):

```
Private key (hex): 9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60
Public key (hex):  d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a
Public key (b64):  11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo=
```

## Test Vector 1: Well-Known

**File:** `well-known-signed.json` — A valid `.well-known/ai-market.json` response.

## Test Vector 2: Manifest

**File:** `manifest-signed.json` — A valid manifest with Ed25519 signature.

**Canonical signing bytes (for verification):**
```
capabilities_count:5|generated_at:2026-05-21T12:00:00Z|protocol_version:v1
```

**Signature (base64):** `1si0V7...`

## Test Vector 3: Receipt

**File:** `receipt-signed.json` — A valid signed receipt.

## Verification

```python
from nacl.signing import VerifyKey
import json, base64

vk = VerifyKey(base64.b64decode("11qYAYKxCrfVS/7TyWQHOg7hcvPapiMlrwIaaPcHURo="))
canonical = b"capabilities_count:5|generated_at:2026-05-21T12:00:00Z|protocol_version:v1"
signature = base64.b64decode("...")
vk.verify(canonical, signature)  # Returns canonical bytes on success, raises on failure
```
