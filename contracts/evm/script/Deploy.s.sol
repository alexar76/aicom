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

        // INITIAL_HUBS must be set explicitly — no dev-default that could ship
        // a useless 0x111…111 hub to mainnet via a forgotten env var. Likewise
        // INITIAL_TOKENS — the same USDC address is not valid across networks
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

        // Sanity: reject the zero address — a parser glitch (trailing comma,
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
    function parseAddress(string memory addrStr) internal pure returns (address) {
        bytes memory b = bytes(addrStr);
        // Strip 0x prefix if present
        uint256 start = 0;
        if (b.length >= 2 && b[0] == "0" && (b[1] == "x" || b[1] == "X")) {
            start = 2;
        }

        uint160 addr = 0;
        for (uint256 i = start; i < b.length; i++) {
            uint8 digit = uint8(b[i]);
            if (digit >= 48 && digit <= 57) {
                addr = (addr << 4) | uint160(digit - 48);
            } else if (digit >= 97 && digit <= 102) {
                addr = (addr << 4) | uint160(digit - 87);
            } else if (digit >= 65 && digit <= 70) {
                addr = (addr << 4) | uint160(digit - 55);
            }
        }

        return address(addr);
    }
}
