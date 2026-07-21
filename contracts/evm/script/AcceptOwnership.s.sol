// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {Script, console} from "forge-std/Script.sol";
import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";

/**
 * @title AcceptOwnershipScript
 * @notice Accept pending ownership of AIMarket contracts when the pending
 *         owner is an EOA.
 *
 * ⚠️  IMPORTANT — this script DOES NOT work for a Gnosis Safe (or any
 * contract-wallet) pending owner.
 *
 * acceptOwnership() in Ownable2Step requires `msg.sender == pendingOwner`.
 * When the pending owner is a Safe contract address, the call MUST originate
 * from the Safe — i.e. produced by a Safe transaction signed by N-of-M
 * owners. Running this script under `forge --broadcast --private-key=<EOA>`
 * sends from the EOA, so `msg.sender != pendingOwner` and the tx reverts
 * (you lose gas, ownership stays pending).
 *
 * Use this script ONLY in these cases:
 *   - testnet / dev drills where the pending owner is an EOA you control
 *   - migration flows where pendingOwner is an upgrade-key EOA
 *
 * For a real Gnosis Safe multisig (the production-recommended path),
 * use the Safe Transaction Builder:
 *   1. calldata = $(cast calldata "acceptOwnership()")
 *   2. In the Safe UI, build a transaction:
 *        to:    CONTRACT_ADDRESS
 *        data:  <calldata>
 *        value: 0
 *   3. Collect N-of-M signatures.
 *   4. Execute.
 *
 * Usage (this script, EOA path):
 *   SAFE_ADDRESS=0xPendingOwnerEOA \
 *   CONTRACT_ADDRESS=0xEscrowAddress \
 *   PRIVATE_KEY=0xPendingOwnerEOAKey \
 *     forge script script/AcceptOwnership.s.sol \
 *       --rpc-url base-sepolia --broadcast
 *
 * The script refuses to broadcast if the pending owner has bytecode (i.e.
 * is a contract) so you cannot accidentally burn gas trying to call
 * acceptOwnership from an EOA against a Safe pending owner.
 */
contract AcceptOwnershipScript is Script {
    function run() external {
        address contractAddr = vm.envAddress("CONTRACT_ADDRESS");
        address safeAddr = vm.envAddress("SAFE_ADDRESS");

        console.log("Contract: %s", contractAddr);
        console.log("Pending owner (env): %s", safeAddr);

        // Verify: the contract's pendingOwner() must be the env-provided address
        address pending = Ownable2Step(contractAddr).pendingOwner();
        require(
            pending == safeAddr,
            "SAFE_ADDRESS does not match contract pendingOwner()"
        );

        console.log("Pending owner verified: %s", pending);
        console.log("Current owner: %s", Ownable2Step(contractAddr).owner());

        // N-2: refuse early if pending owner is a contract — acceptOwnership
        // would revert (msg.sender = forge EOA != pendingOwner = Safe contract).
        // Tell the operator exactly what to do instead.
        require(
            !_isContract(pending),
            "Pending owner is a contract (e.g. Gnosis Safe). Use the Safe Transaction Builder: cast calldata 'acceptOwnership()' -> Safe tx to=CONTRACT_ADDRESS,data=<calldata>,value=0. See docstring."
        );

        uint256 ownerPrivateKey = vm.envUint("PRIVATE_KEY");
        address signer = vm.addr(ownerPrivateKey);
        console.log("Signer: %s", signer);
        require(
            signer == pending,
            "PRIVATE_KEY address does not match pendingOwner -- accept would revert"
        );

        vm.startBroadcast(ownerPrivateKey);

        Ownable2Step(contractAddr).acceptOwnership();

        vm.stopBroadcast();

        // Verify transfer completed
        address newOwner = Ownable2Step(contractAddr).owner();
        require(newOwner == safeAddr, "Ownership transfer failed");
        console.log("Ownership accepted. New owner: %s", newOwner);
        console.log("Done.");
    }

    /// @dev True if `addr` has bytecode. EOAs have empty extcodesize.
    function _isContract(address addr) internal view returns (bool) {
        uint256 size;
        assembly {
            size := extcodesize(addr)
        }
        return size > 0;
    }
}
