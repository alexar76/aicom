# AIMarket contracts — usage examples

> **Audit recommendation:** Before mainnet, commission an **independent third-party audit** of
> `AIMarketEscrow.sol`, `AIMarketCapabilityNFT.sol`, and the Solana escrow program. Track
> findings in [`audits/audit-response.md`](audits/audit-response.md) and run Slither locally via
> [`../scripts/run_contract_audit.sh`](../scripts/run_contract_audit.sh). Internal reviews live in
> [`audits/PAYMENT_LAYER_SECURITY_AUDIT.md`](audits/PAYMENT_LAYER_SECURITY_AUDIT.md) — they do **not**
> replace external audit.

**Status:** Pre-mainnet — testnet drills only until KI-2…KI-5 in [`../docs/known-issues.md`](../docs/known-issues.md) are closed.

---

## 1. EVM — open a payment channel

```solidity
// SPDX-License-Identifier: MIT
import {AIMarketEscrow} from "./AIMarketEscrow.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

AIMarketEscrow escrow = AIMarketEscrow(escrowAddress);
IERC20 usdc = IERC20(usdcAddress);

uint256 deposit = 100e6; // 100 USDC (6 decimals)
usdc.approve(address(escrow), deposit);
escrow.openChannel(provider, deposit);
```

Full Foundry tests: [`evm/test/AIMarketEscrow.t.sol`](evm/test/AIMarketEscrow.t.sol).

---

## 2. EVM — EIP-712 debit authorization (off-chain sign → on-chain debit)

The hub and SDKs sign a **DebitAuthorization** struct compatible with `AIMarketEscrow.debitChannel`.

**TypeScript (aimarket-sdks):**

```typescript
import { MarketSigner } from "@aimarket/sdk";

const signer = MarketSigner.fromPrivateKey(process.env.EVM_PRIVATE_KEY!);
const sig = signer.signDebitAuthorization({
  channelId: "0x…",
  amount: 1_000_000n, // token minor units
  nonce: 1n,
  chainId: 8453,
  verifyingContract: escrowAddress,
});
// sig.format → eip712:0x<r><s><v> — pass to hub invoke / settlement path
```

Cross-language vectors: [`../aimarket-sdks/test-vectors/debit_authorization.json`](https://github.com/alexar76/aimarket-sdks/blob/main/test-vectors/debit_authorization.json).

**Python (hub channel settlement):**

```python
from aimarket_hub.channels import ChannelStore

store = ChannelStore(path="data/channels.db")
# open_channel / debit_with_signature — see tests/test_channels.py
```

---

## 3. Deploy to testnet

```bash
cd contracts/evm
cp .env.example .env   # RPC_URL, DEPLOYER_KEY, USDC_ADDRESS
forge test -vv
./deploy.sh            # or: forge script script/Deploy.s.sol --rpc-url $RPC_URL --broadcast
```

Runbook: [`DEPLOY.md`](DEPLOY.md). Transfer ownership after deploy: [`evm/script/AcceptOwnership.s.sol`](evm/script/AcceptOwnership.s.sol).

---

## 4. Solana — escrow program

```bash
cd contracts/solana
anchor test   # 7 scenarios in tests/aimarket_escrow.ts
```

Program layout: [`solana/programs/aimarket-escrow/`](solana/programs/aimarket-escrow/).

---

## 5. ZK — PLONK input validity (optional settlement helper)

```bash
cd contracts/zk
npm install
bash scripts/setup_plonk.sh   # universal setup — no ceremony

export AIMARKET_ZK_BACKEND=plonk
export AIMARKET_ZK_WASM=$PWD/build/input_validity_js/input_validity.wasm
export AIMARKET_ZK_ZKEY=$PWD/build/input_validity_plonk.zkey
export AIMARKET_ZK_VKEY_JSON=$PWD/verifier/verification_key.json
# unset AIMARKET_ZK_SIMULATED for real proofs
```

Details: [`zk/README.md`](zk/README.md), ceremony (Groth16 optional): [`zk/ZK_CEREMONY.md`](zk/ZK_CEREMONY.md).

---

## 6. Local Anvil drill (factory + Alien Monitor)

See [`../docs/uni-troubleshooting.md`](../docs/uni-troubleshooting.md) — spin Anvil, deploy escrow, wire `.env`, invoke via hub sandbox.

---

## 7. Coverage & CI

```bash
cd contracts/evm && make coverage   # forge coverage (local)
cd contracts/evm && forge test -vv
```

Factory CI runs backend + contract integration tests; satellite **acex** runs `forge test` on every push.
