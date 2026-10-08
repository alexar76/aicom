// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {Script, console} from "forge-std/Script.sol";
import {AIMarketEscrowV2} from "../src/AIMarketEscrowV2.sol";

/**
 * @title DeployEscrowV2
 * @notice Deploy AIMarketEscrowV2 with exactly one authorized hub and one whitelisted token.
 *
 * The live rail has one of each (HORKOS, Base USDC), so this takes two addresses instead of
 * DeployScript's comma-separated lists: `vm.envAddress` validates each one strictly, and
 * there is no parser between the environment and the constructor. Run it through
 * scripts/deploy_escrow_lottery_base.sh, which pins both and keeps the key out of argv.
 */
contract DeployEscrowV2 is Script {
    function run() external returns (AIMarketEscrowV2 escrow) {
        address hub = vm.envAddress("INITIAL_HUB");
        address token = vm.envAddress("INITIAL_TOKEN");
        require(hub != address(0), "INITIAL_HUB is the zero address");
        require(token != address(0), "INITIAL_TOKEN is the zero address");

        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerKey);
        console.log("Deployer: %s", deployer);
        console.log("Hub:      %s", hub);
        console.log("Token:    %s", token);

        address[] memory hubs = new address[](1);
        hubs[0] = hub;
        address[] memory tokens = new address[](1);
        tokens[0] = token;

        vm.startBroadcast(deployerKey);
        escrow = new AIMarketEscrowV2(hubs, tokens);
        vm.stopBroadcast();

        require(escrow.authorizedHubs(hub), "hub not authorized");
        require(escrow.whitelistedTokens(token), "token not whitelisted");
        require(escrow.SETTLE_WINDOW() == 1 hours, "unexpected SETTLE_WINDOW");
        require(escrow.owner() == deployer, "owner is not the deployer");

        console.log("AIMarketEscrowV2 deployed at: %s", address(escrow));
        console.log("Chain ID: %d", block.chainid);
    }
}
