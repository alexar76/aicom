// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {Script, console2} from "forge-std/Script.sol";

import {AgentCollateralVault} from "../src/AgentCollateralVault.sol";
import {AgentListingRegistry} from "../src/AgentListingRegistry.sol";
import {AgentLendingPool} from "../src/AgentLendingPool.sol";
import {PulseAMM} from "../src/PulseAMM.sol";

/// @notice Deploy ACEX EVM stack. Set USDC_ADDRESS in env.
/// forge script script/DeployACEX.s.sol --rpc-url $RPC --broadcast
contract DeployACEX is Script {
    function run() external {
        address usdc = vm.envAddress("USDC_ADDRESS");
        uint256 deployerKey = vm.envUint("DEPLOYER_PRIVATE_KEY");

        vm.startBroadcast(deployerKey);

        AgentCollateralVault vault = new AgentCollateralVault(usdc);
        AgentListingRegistry registry = new AgentListingRegistry(address(vault), usdc);
        vault.setRegistry(address(registry));
        AgentLendingPool lending = new AgentLendingPool(usdc, address(vault), address(registry));
        vault.setLendingPool(address(lending));
        PulseAMM amm = new PulseAMM();

        vm.stopBroadcast();

        console2.log("AgentCollateralVault", address(vault));
        console2.log("AgentListingRegistry", address(registry));
        console2.log("AgentLendingPool", address(lending));
        console2.log("PulseAMM", address(amm));
    }
}
