// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {Script, console} from "forge-std/Script.sol";
import {BountySplitter} from "../src/BountySplitter.sol";

/**
 * @title DeployBountySplitter
 * @notice Deploy the MOMUS bounty settlement backend.
 *
 * The deployer becomes the OWNER, i.e. the Treasury operator: the only address that can fund a
 * pool or release a share. Deploy this from the Treasury's key, NOT from the MOMUS scanner key —
 * the whole design rests on those being different principals.
 *
 * Settlement is opt-in twice over (see momus/momus/settlement.py): the ecosystem crypto master
 * switch AND a separate MOMUS_BOUNTY_ONCHAIN=1 must both be set before MOMUS will even prepare an
 * on-chain call, and MOMUS never broadcasts one itself. Until an operator wires this address into
 * MOMUS_BOUNTY_SPLITTER, the whole loop runs in the UNI simulation with no value moving.
 *
 * Usage:
 *   # Base Sepolia (testnet — do this first)
 *   PRIVATE_KEY=0x... BOUNTY_TOKENS=<usdc-address> \
 *     forge script script/DeployBountySplitter.s.sol --rpc-url base-sepolia --broadcast --verify
 *
 *   # Base mainnet (REAL funds: the owner key controls every release)
 *   PRIVATE_KEY=0x... BOUNTY_TOKENS=0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 \
 *     forge script script/DeployBountySplitter.s.sol --rpc-url base-mainnet --broadcast --verify
 *
 *   # Local anvil, for a dry run
 *   PRIVATE_KEY=0xac09... BOUNTY_TOKENS=<mock> \
 *     forge script script/DeployBountySplitter.s.sol --rpc-url http://127.0.0.1:8545 --broadcast
 *
 * After deploying, set on the MOMUS/Treasury host:
 *   MOMUS_BOUNTY_SPLITTER=<deployed address>
 *   MOMUS_BOUNTY_TOKEN=<the settlement token>
 *   MOMUS_BOUNTY_CHAIN=base
 *   MOMUS_BOUNTY_ONCHAIN=1        # the separate bounty opt-in
 *   AIFACTORY_CRYPTO_ENABLED=1    # the ecosystem crypto master switch
 */
contract DeployBountySplitter is Script {
    function run() external returns (BountySplitter splitter) {
        uint256 pk = vm.envUint("PRIVATE_KEY");
        address[] memory tokens = _tokens();

        vm.startBroadcast(pk);
        splitter = new BountySplitter(tokens);
        vm.stopBroadcast();

        console.log("BountySplitter deployed at:", address(splitter));
        console.log("Owner (Treasury operator):", vm.addr(pk));
        for (uint256 i = 0; i < tokens.length; i++) {
            console.log("  whitelisted token:", tokens[i]);
        }
        console.log("Next: set MOMUS_BOUNTY_SPLITTER to the address above, then");
        console.log("      MOMUS_BOUNTY_ONCHAIN=1 + AIFACTORY_CRYPTO_ENABLED=1 to leave UNI mode.");
    }

    /// @dev BOUNTY_TOKENS: comma-separated ERC-20 addresses (USDC/USDT on the target chain).
    function _tokens() internal view returns (address[] memory out) {
        string memory raw = vm.envOr("BOUNTY_TOKENS", string(""));
        if (bytes(raw).length == 0) {
            out = new address[](0);
            return out;
        }
        string[] memory parts = vm.split(raw, ",");
        out = new address[](parts.length);
        for (uint256 i = 0; i < parts.length; i++) {
            out[i] = vm.parseAddress(parts[i]);
        }
    }
}
