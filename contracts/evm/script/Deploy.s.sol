// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {Script, console} from "forge-std/Script.sol";
import {AIMarketEscrow} from "../src/AIMarketEscrow.sol";

/**
 * @title DeployScript
 * @notice Deploy AIMarketEscrow with initial authorized hubs and whitelisted tokens.
 *
 * Usage:
 *   # Deploy to Base Sepolia
 *   PRIVATE_KEY=0x... RPC_BASE_SEPOLIA=<url> forge script script/Deploy.s.sol \
 *       --rpc-url base-sepolia --broadcast --verify
 *
 *   # Deploy to Base Mainnet
 *   PRIVATE_KEY=0x... RPC_BASE_MAINNET=<url> forge script script/Deploy.s.sol \
 *       --rpc-url base-mainnet --broadcast --verify
 */
contract DeployScript is Script {
    /// @notice Initial hub addresses authorized to debit channels.
    ///         Override via environment variable INITIAL_HUBS (comma-separated).
    ///         Default: a single dev hub address.
    address[] public initialHubs;

    /// @notice Initial ERC-20 tokens whitelisted for deposits.
    ///         Override via environment variable INITIAL_TOKENS (comma-separated).
    ///         Default: USDC on Base mainnet.
    address[] public initialTokens;

    function run() external returns (AIMarketEscrow) {
        // ── Read constructor args ───────────────────────────────────
        string memory hubsEnv = vm.envOr("INITIAL_HUBS", string(""));
        string memory tokensEnv = vm.envOr("INITIAL_TOKENS", string(""));

        // INITIAL_HUBS must be set explicitly -- no dev-default that could ship
        // a useless 0x111...111 hub to mainnet via a forgotten env var. Likewise
        // INITIAL_TOKENS -- the same USDC address is not valid across networks
        // (mainnet/sepolia/arbitrum all differ), and a wrong default is worse
        // than a missing one.
        require(
            bytes(hubsEnv).length > 0,
            "INITIAL_HUBS is required (comma-separated authorized hub addresses)"
        );
        require(
            bytes(tokensEnv).length > 0,
            "INITIAL_TOKENS is required (comma-separated whitelisted ERC-20 token addresses for this chain)"
        );

        initialHubs = parseAddressList(hubsEnv);
        initialTokens = parseAddressList(tokensEnv);

        // Sanity: reject the zero address -- a parser glitch (trailing comma,
        // empty entry) would otherwise silently authorize address(0).
        for (uint256 i = 0; i < initialHubs.length; i++) {
            require(initialHubs[i] != address(0), "INITIAL_HUBS contains zero address");
        }
        for (uint256 i = 0; i < initialTokens.length; i++) {
            require(initialTokens[i] != address(0), "INITIAL_TOKENS contains zero address");
        }

        // ── Deploy ──────────────────────────────────────────────────
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerPrivateKey);

        console.log("Deployer address: %s", deployer);
        console.log("Initial hubs: %d", initialHubs.length);
        for (uint256 i = 0; i < initialHubs.length; i++) {
            console.log("  hub[%d]: %s", i, initialHubs[i]);
        }
        console.log("Initial tokens: %d", initialTokens.length);
        for (uint256 i = 0; i < initialTokens.length; i++) {
            console.log("  token[%d]: %s", i, initialTokens[i]);
        }

        vm.startBroadcast(deployerPrivateKey);

        AIMarketEscrow escrow = new AIMarketEscrow(initialHubs, initialTokens);

        vm.stopBroadcast();

        // ── Verify ───────────────────────────────────────────────────
        console.log("AIMarketEscrow deployed at: %s", address(escrow));
        console.log("Chain ID: %d", block.chainid);

        // Verify constructor params were stored correctly
        assert(escrow.authorizedHubs(initialHubs[0]));
        assert(escrow.whitelistedTokens(initialTokens[0]));

        console.log("Constructor params verified on-chain.");

        // ── Ownership transfer to multisig ──────────────────────────
        // If SAFE_ADDRESS is set, initiate the two-step ownership transfer
        // to a Gnosis Safe (or any multisig). The Safe must call
        // acceptOwnership() separately (see script/AcceptOwnership.s.sol).
        //
        // SECURITY (N-1): use vm.envOr(string,address) — Foundry validates the
        // 0x-prefixed 40-hex-char address format and reverts on malformed input.
        // The earlier parseAddress() silently accepted any prefix length
        // (e.g. SAFE_ADDRESS="0xabc" → 0x0000…abc), which would have routed
        // ownership to an unrecoverable address.
        address safe = vm.envOr("SAFE_ADDRESS", address(0));
        if (safe != address(0)) {
            console.log("Initiating ownership transfer to Safe: %s", safe);
            escrow.transferOwnership(safe);
            console.log("Ownership transfer initiated. Safe must call acceptOwnership().");
        } else {
            console.log("SAFE_ADDRESS not set -- deployer retains ownership.");
            console.log("For production, re-run with SAFE_ADDRESS=<multisig>.");
        }

        console.log("Deployment complete.");

        return escrow;
    }

    /// @notice Parse a comma-separated string of addresses into an array.
    function parseAddressList(string memory input) internal pure returns (address[] memory) {
        bytes memory inputBytes = bytes(input);
        if (inputBytes.length == 0) {
            return new address[](0);
        }

        // Count commas
        uint256 count = 1;
        for (uint256 i = 0; i < inputBytes.length; i++) {
            if (inputBytes[i] == ",") {
                count++;
            }
        }

        address[] memory result = new address[](count);
        uint256 index = 0;
        bytes memory current = new bytes(0);

        for (uint256 i = 0; i < inputBytes.length; i++) {
            if (inputBytes[i] == ",") {
                result[index] = parseAddress(string(current));
                index++;
                current = new bytes(0);
            } else {
                bytes memory newCurrent = new bytes(current.length + 1);
                for (uint256 j = 0; j < current.length; j++) {
                    newCurrent[j] = current[j];
                }
                newCurrent[current.length] = inputBytes[i];
                current = newCurrent;
            }
        }
        if (current.length > 0) {
            result[index] = parseAddress(string(current));
        }

        return result;
    }

    /// @notice Convert a hex address string to address type.
    /// @dev STRICT: trims surrounding whitespace, requires exactly 40 hex chars
    ///      (after an optional 0x/0X prefix), and REVERTS on any non-hex
    ///      character or wrong length. The previous parser silently skipped
    ///      invalid characters and never checked length, so a typo, stray
    ///      character, or truncated entry produced a different, non-zero address
    ///      baked into the constructor as an authorized hub / whitelisted token
    ///      on a mainnet deploy. Failing loudly is mandatory here.
    function parseAddress(string memory addrStr) internal pure returns (address) {
        bytes memory raw = bytes(addrStr);
        // Trim ASCII spaces/tabs so "a, b"-style env lists parse cleanly.
        uint256 lo = 0;
        uint256 hi = raw.length;
        while (lo < hi && (raw[lo] == 0x20 || raw[lo] == 0x09)) lo++;
        while (hi > lo && (raw[hi - 1] == 0x20 || raw[hi - 1] == 0x09)) hi--;

        uint256 start = lo;
        if (hi - start >= 2 && raw[start] == "0" && (raw[start + 1] == "x" || raw[start + 1] == "X")) {
            start += 2;
        }
        require(hi - start == 40, "parseAddress: expected a 40-hex-char address");

        uint160 addr = 0;
        for (uint256 i = start; i < hi; i++) {
            uint8 digit = uint8(raw[i]);
            uint160 val;
            if (digit >= 48 && digit <= 57) {
                val = uint160(digit - 48);
            } else if (digit >= 97 && digit <= 102) {
                val = uint160(digit - 87);
            } else if (digit >= 65 && digit <= 70) {
                val = uint160(digit - 55);
            } else {
                revert("parseAddress: invalid hex character");
            }
            addr = (addr << 4) | val;
        }

        return address(addr);
    }
}
