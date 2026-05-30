// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script, console} from "forge-std/Script.sol";
import {FakeUSDT} from "../src/FakeUSDT.sol";

contract DeployFakeUSDTScript is Script {
    function run() external returns (FakeUSDT) {
        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");
        address deployer = vm.addr(deployerPrivateKey);
        console.log("Deployer: %s", deployer);

        vm.startBroadcast(deployerPrivateKey);
        FakeUSDT token = new FakeUSDT();
        vm.stopBroadcast();

        console.log("FakeUSDT deployed at: %s", address(token));
        return token;
    }
}
