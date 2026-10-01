// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script, console} from "forge-std/Script.sol";
import {FakeUSDT} from "../src/FakeUSDT.sol";

/**
 * @title DeployFakeUSDTScript
 * @notice Deploy the FakeUSDT test token for local Anvil / UNI mode only.
 *
 * SECURITY: FakeUSDT mints 1,000,000 unbacked "USDT" to the deployer and must
 * NEVER reach a public network where it could be mistaken for real USDT. This
 * script therefore refuses to broadcast unless one of the following holds:
 *   - the target chain is a well-known local devnet (Anvil/Hardhat 31337/1337), or
 *   - the operator has explicitly set ALLOW_FAKE_USDT=true to override.
 *
 * Usage:
 *   # Local Anvil (default chainid 31337) -- no override needed
 *   PRIVATE_KEY=0x... forge script script/DeployFakeUSDT.s.sol \
 *       --rpc-url http://127.0.0.1:8545 --broadcast
 *
 *   # Any other chain (e.g. an ephemeral testnet fork) -- explicit opt-in
 *   ALLOW_FAKE_USDT=true PRIVATE_KEY=0x... forge script script/DeployFakeUSDT.s.sol \
 *       --rpc-url <url> --broadcast
 */
contract DeployFakeUSDTScript is Script {
    /// @dev Anvil's default chain id.
    uint256 internal constant ANVIL_CHAIN_ID = 31337;
    /// @dev Hardhat's default chain id (also used by some local devnets).
    uint256 internal constant HARDHAT_CHAIN_ID = 1337;

    function run() external returns (FakeUSDT) {
        // ── Local-only guard ─────────────────────────────────────────
        // Block deployment to any non-local chain unless explicitly allowed.
        // vm.envOr(string,bool) defaults to false when ALLOW_FAKE_USDT is unset.
        bool allowOverride = vm.envOr("ALLOW_FAKE_USDT", false);
        bool isLocalChain =
            block.chainid == ANVIL_CHAIN_ID || block.chainid == HARDHAT_CHAIN_ID;

        if (!isLocalChain) {
            console.log("Refusing to deploy FakeUSDT on chain id: %d", block.chainid);
        }
        require(
            isLocalChain || allowOverride,
            "FakeUSDT is a local-only test token: deploy on Anvil/Hardhat (chainid 31337/1337) or set ALLOW_FAKE_USDT=true to override"
        );

        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerPrivateKey);
        console.log("Deployer: %s", deployer);
        console.log("Chain ID: %d", block.chainid);
        if (allowOverride && !isLocalChain) {
            console.log("WARNING: ALLOW_FAKE_USDT override active on a non-local chain.");
        }

        vm.startBroadcast(deployerPrivateKey);
        FakeUSDT token = new FakeUSDT();
        vm.stopBroadcast();

        console.log("FakeUSDT deployed at: %s", address(token));
        return token;
    }
}
