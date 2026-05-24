// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {Script, console} from "forge-std/Script.sol";
import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";

/**
 * @title AcceptOwnershipScript
 * @notice Accept pending ownership of AIMarket contracts from a Gnosis Safe
 *         (or any EOA/multisig that is the pending owner).
 *
 * This is step 2 of the two-step ownership transfer initiated by the deploy
 * scripts. After Deploy.s.sol (or DeployNFT.s.sol) calls `transferOwnership(safe)`,
 * the Safe signers coordinate to broadcast this script.
 *
 * Usage (Safe UI / multisig):
 *   # For the escrow contract
 *   SAFE_ADDRESS=0xYourSafe... \
 *   CONTRACT_ADDRESS=0xEscrowAddress... \
 *   PRIVATE_KEY=0xOneOfTheSafeSigners... \
 *     forge script script/AcceptOwnership.s.sol \
 *       --rpc-url base-mainnet --broadcast
 *
 *   # For the NFT contract
 *   CONTRACT_ADDRESS=0xNFTAddress... \
 *     forge script script/AcceptOwnership.s.sol \
 *       --rpc-url base-mainnet --broadcast
 *
 * Usage (Safe Transaction Builder — recommended for multisig):
 *   1. Build calldata: cast calldata "acceptOwnership()"
 *   2. Create Safe transaction with `to = CONTRACT_ADDRESS`,
 *      `data = <calldata>`, `value = 0`.
 *   3. Collect N-of-M signatures.
 *   4. Execute.
 *
 * Either approach works — this script is the forge-native path; the Safe UI
 * path uses raw calldata.
 */
contract AcceptOwnershipScript is Script {
    function run() external {
        address contractAddr = vm.envAddress("CONTRACT_ADDRESS");
        address safeAddr = vm.envAddress("SAFE_ADDRESS");

        console.log("Contract: %s", contractAddr);
        console.log("Safe (pending owner): %s", safeAddr);

        // Verify: the contract's pendingOwner() must be the Safe
        address pending = Ownable2Step(contractAddr).pendingOwner();
        require(
            pending == safeAddr,
            "SAFE_ADDRESS does not match contract pendingOwner()"
        );

        console.log("Pending owner verified: %s", pending);
        console.log("Current owner: %s", Ownable2Step(contractAddr).owner());

        uint256 deployerPrivateKey = vm.envUint("PRIVATE_KEY");
        address signer = vm.addr(deployerPrivateKey);
        console.log("Signer: %s", signer);

        vm.startBroadcast(deployerPrivateKey);

        Ownable2Step(contractAddr).acceptOwnership();

        vm.stopBroadcast();

        // Verify transfer completed
        address newOwner = Ownable2Step(contractAddr).owner();
        require(newOwner == safeAddr, "Ownership transfer failed");
        console.log("Ownership accepted. New owner: %s", newOwner);
        console.log("Done.");
    }
}
