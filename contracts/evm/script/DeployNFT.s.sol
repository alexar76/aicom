// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {Script, console} from "forge-std/Script.sol";
import {AIMarketCapabilityNFT} from "../src/AIMarketCapabilityNFT.sol";

/**
 * @title DeployCapabilityNFT
 * @notice Deploy AIMarketCapabilityNFT and authorize initial hubs.
 *
 * Usage:
 *   PRIVATE_KEY=0x... \
 *   INITIAL_HUBS=0x111...,0x222... \
 *   forge script script/DeployNFT.s.sol --rpc-url base-sepolia --broadcast --verify
 */
contract DeployCapabilityNFTScript is Script {
    function run() external returns (AIMarketCapabilityNFT) {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerPrivateKey);

        string memory hubsEnv = vm.envOr("INITIAL_HUBS", string(""));
        address[] memory initialHubs;
        if (bytes(hubsEnv).length > 0) {
            initialHubs = _parseAddresses(hubsEnv);
        }

        console.log("Deployer: %s", deployer);
        console.log("Initial authorized hubs: %d", initialHubs.length);

        vm.startBroadcast(deployerPrivateKey);

        AIMarketCapabilityNFT nft = new AIMarketCapabilityNFT();
        for (uint256 i = 0; i < initialHubs.length; i++) {
            nft.setAuthorizedHub(initialHubs[i], true);
            console.log("  authorized hub[%d]: %s", i, initialHubs[i]);
        }

        vm.stopBroadcast();

        console.log("AIMarketCapabilityNFT deployed at: %s", address(nft));
        console.log("Chain ID: %d", block.chainid);
        console.log("Owner: %s", nft.owner());

        // ── Ownership transfer to multisig ──────────────────────────
        // SECURITY (N-1): vm.envOr(string,address) validates the 0x-prefixed
        // 40-hex-char address format and reverts on malformed input. The
        // earlier _parseHexAddress() silently accepted any prefix length.
        address safe = vm.envOr("SAFE_ADDRESS", address(0));
        if (safe != address(0)) {
            console.log("Initiating ownership transfer to Safe: %s", safe);
            nft.transferOwnership(safe);
            console.log("Ownership transfer initiated. Safe must call acceptOwnership().");
        } else {
            console.log("SAFE_ADDRESS not set -- deployer retains ownership.");
            console.log("For production, re-run with SAFE_ADDRESS=<multisig>.");
        }

        console.log("Deployment complete.");

        return nft;
    }

    function _parseAddresses(string memory input) internal pure returns (address[] memory) {
        bytes memory b = bytes(input);
        if (b.length == 0) return new address[](0);

        uint256 count = 1;
        for (uint256 i = 0; i < b.length; i++) {
            if (b[i] == ",") count++;
        }
        address[] memory result = new address[](count);

        uint256 idx = 0;
        bytes memory cur = new bytes(0);
        for (uint256 i = 0; i < b.length; i++) {
            if (b[i] == ",") {
                result[idx++] = _parseHexAddress(string(cur));
                cur = new bytes(0);
            } else {
                bytes memory next = new bytes(cur.length + 1);
                for (uint256 j = 0; j < cur.length; j++) next[j] = cur[j];
                next[cur.length] = b[i];
                cur = next;
            }
        }
        if (cur.length > 0) result[idx] = _parseHexAddress(string(cur));
        return result;
    }

    /// @dev STRICT hex-address parse: trims whitespace, requires exactly 40 hex
    ///      chars after an optional 0x prefix, and reverts on any non-hex char or
    ///      wrong length — so a typo can't bake a wrong-but-nonzero address into a
    ///      mainnet deploy (previously invalid chars were silently skipped).
    function _parseHexAddress(string memory s) internal pure returns (address) {
        bytes memory raw = bytes(s);
        uint256 lo = 0;
        uint256 hi = raw.length;
        while (lo < hi && (raw[lo] == 0x20 || raw[lo] == 0x09)) lo++;
        while (hi > lo && (raw[hi - 1] == 0x20 || raw[hi - 1] == 0x09)) hi--;

        uint256 start = lo;
        if (hi - start >= 2 && raw[start] == "0" && (raw[start + 1] == "x" || raw[start + 1] == "X")) {
            start += 2;
        }
        require(hi - start == 40, "parseHexAddress: expected a 40-hex-char address");

        uint160 addr = 0;
        for (uint256 i = start; i < hi; i++) {
            uint8 c = uint8(raw[i]);
            uint160 val;
            if (c >= 48 && c <= 57) val = uint160(c - 48);
            else if (c >= 97 && c <= 102) val = uint160(c - 87);
            else if (c >= 65 && c <= 70) val = uint160(c - 55);
            else revert("parseHexAddress: invalid hex character");
            addr = (addr << 4) | val;
        }
        return address(addr);
    }
}
