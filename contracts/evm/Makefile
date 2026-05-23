# ── AI Market Escrow — Foundry Makefile ───────────────────────────────────────

.PHONY: build test test-verbose test-gas coverage deploy-sepolia deploy-base slither verify

# ── Build ─────────────────────────────────────────────────────────────────────

build:
	forge build

# ── Test ──────────────────────────────────────────────────────────────────────

test:
	forge test

test-verbose:
	forge test -vvv

test-gas:
	forge test --gas-report

coverage:
	forge coverage
	@echo "Coverage report: coverage/index.html"

# ── Deploy ────────────────────────────────────────────────────────────────────

deploy-sepolia:
	forge script script/Deploy.s.sol \
		--rpc-url base-sepolia \
		--broadcast \
		--verify \
		--etherscan-api-key ${BASESCAN_API_KEY}

deploy-base:
	forge script script/Deploy.s.sol \
		--rpc-url base-mainnet \
		--broadcast \
		--verify \
		--etherscan-api-key ${BASESCAN_API_KEY}

# ── Static Analysis ───────────────────────────────────────────────────────────

slither:
	slither . --config-file slither.config.json

# ── Verification ──────────────────────────────────────────────────────────────

verify:
	@echo "Usage: forge verify-contract <address> <contract-path> --chain <chain-id>"
	@echo "Example:"
	@echo "  forge verify-contract 0x... src/AIMarketEscrow.sol:AIMarketEscrow --chain 8453"
