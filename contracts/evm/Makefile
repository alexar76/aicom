# ── AI Market Escrow — Foundry Makefile ───────────────────────────────────────

.PHONY: install build test test-verbose test-gas coverage deploy-sepolia deploy-base slither verify

# ── Install ───────────────────────────────────────────────────────────────────
# `forge install` requires a clean git submodule state in the parent repo;
# the aicom monorepo has unrelated gitlinks (`coach/`) which break that path.
# Clone the two deps directly into lib/ instead — same result, no submodule
# entanglement. Run once after `git clone`; `lib/` is in `.gitignore`.
OZ_VERSION ?= v5.0.2
install:
	@mkdir -p lib
	@if [ ! -d lib/openzeppelin-contracts ]; then \
		git clone --depth=1 --branch $(OZ_VERSION) \
			https://github.com/OpenZeppelin/openzeppelin-contracts.git \
			lib/openzeppelin-contracts; \
	fi
	@if [ ! -d lib/forge-std ]; then \
		git clone --depth=1 \
			https://github.com/foundry-rs/forge-std.git \
			lib/forge-std; \
	fi
	@echo "Deps ready (lib/openzeppelin-contracts $(OZ_VERSION), lib/forge-std)."

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
