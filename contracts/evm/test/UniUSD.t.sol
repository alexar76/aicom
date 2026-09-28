// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {Test, Vm} from "forge-std/Test.sol";
import {UniUSD} from "../src/UniUSD.sol";

/// The bubble's dollar must look like Base USDC to anything that reads its logs. The hub finds a
/// payment by the topic of `AuthorizationUsed(address,bytes32)` (settle.AUTHORIZATION_USED_TOPIC)
/// followed by the authorization's own `Transfer`; a token that logged anything else could take
/// the money and never be seen to.
contract UniUSDTest is Test {
    bytes32 constant USDC_AUTHORIZATION_USED =
        0x98de503528ee59b575ef0c0a2576a82497bfc029a5685b209e9ec333479b10a5;
    bytes32 constant TRANSFER = keccak256("Transfer(address,address,uint256)");

    UniUSD token;
    uint256 payerKey = 0xA11CE;
    address payer;
    address payee = address(0xBEEF);

    function setUp() public {
        token = new UniUSD();
        payer = vm.addr(payerKey);
        token.mint(payer, 10_000_000);
    }

    function _sign(uint256 value, bytes32 nonce, uint256 validBefore) internal view returns (uint8, bytes32, bytes32) {
        bytes32 structHash = keccak256(abi.encode(
            token.TRANSFER_WITH_AUTHORIZATION_TYPEHASH(), payer, payee, value, uint256(0), validBefore, nonce
        ));
        bytes32 digest = keccak256(abi.encodePacked("\x19\x01", token.domainSeparator(), structHash));
        return vm.sign(payerKey, digest);
    }

    function test_the_authorization_logs_usdc_topic_then_its_own_transfer() public {
        bytes32 nonce = keccak256("quote-1");
        (uint8 v, bytes32 r, bytes32 s) = _sign(5_000_000, nonce, block.timestamp + 600);
        vm.recordLogs();
        token.transferWithAuthorization(payer, payee, 5_000_000, 0, block.timestamp + 600, nonce, v, r, s);
        Vm.Log[] memory logs = vm.getRecordedLogs();
        assertEq(logs.length, 2);
        assertEq(logs[0].topics[0], USDC_AUTHORIZATION_USED);
        assertEq(logs[0].topics[1], bytes32(uint256(uint160(payer))));
        assertEq(logs[0].topics[2], nonce);
        assertEq(logs[1].topics[0], TRANSFER);
        assertEq(token.balanceOf(payee), 5_000_000);
    }

    function test_a_nonce_pays_once() public {
        bytes32 nonce = keccak256("quote-2");
        (uint8 v, bytes32 r, bytes32 s) = _sign(1_000_000, nonce, block.timestamp + 600);
        token.transferWithAuthorization(payer, payee, 1_000_000, 0, block.timestamp + 600, nonce, v, r, s);
        vm.expectRevert(UniUSD.AuthorizationAlreadyUsed.selector);
        token.transferWithAuthorization(payer, payee, 1_000_000, 0, block.timestamp + 600, nonce, v, r, s);
    }
}
