// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {AIMarketCapabilityNFT} from "../src/AIMarketCapabilityNFT.sol";

contract AIMarketCapabilityNFTTest is Test {
    AIMarketCapabilityNFT public nft;

    address public owner;
    address public alice;
    address public bob;
    address public hub;
    address public stranger;

    bytes32 public constant CAP_ID = keccak256("translate.multi@v2");
    bytes32 public constant PROD_ID = keccak256("prod-translate");

    function setUp() public {
        owner = address(this);
        alice = address(0xA11CE);
        bob = address(0xB0B);
        hub = address(0xC0FFEE);
        stranger = address(0xDEAD);

        nft = new AIMarketCapabilityNFT();
        nft.setAuthorizedHub(hub, true);
    }

    // ── Mint ─────────────────────────────────────────────────────

    function test_mint_happyPath() public {
        uint256 tokenId = nft.mint(alice, CAP_ID, PROD_ID, 100, 400_000); // $0.40

        assertEq(nft.ownerOf(tokenId), alice);
        AIMarketCapabilityNFT.Entitlement memory e = nft.getEntitlement(tokenId);
        assertEq(e.capabilityId, CAP_ID);
        assertEq(e.productId, PROD_ID);
        assertEq(e.totalCalls, 100);
        assertEq(e.remainingCalls, 100);
        assertEq(e.pricePerCallUsd6, 400_000);
        assertEq(e.transferCount, 0);
    }

    function test_mint_revertsIfNotOwner() public {
        vm.prank(alice);
        vm.expectRevert();
        nft.mint(alice, CAP_ID, PROD_ID, 100, 400_000);
    }

    function test_mint_revertsOnZeroCalls() public {
        vm.expectRevert(AIMarketCapabilityNFT.InvalidTotalCalls.selector);
        nft.mint(alice, CAP_ID, PROD_ID, 0, 400_000);
    }

    function test_mint_increments_tokenId() public {
        uint256 t1 = nft.mint(alice, CAP_ID, PROD_ID, 100, 400_000);
        uint256 t2 = nft.mint(bob, CAP_ID, PROD_ID, 50, 400_000);
        assertEq(t2, t1 + 1);
    }

    // ── Transfer ─────────────────────────────────────────────────

    function test_transfer_byOwner() public {
        uint256 tokenId = nft.mint(alice, CAP_ID, PROD_ID, 100, 400_000);

        vm.prank(alice);
        nft.transferFrom(alice, bob, tokenId);

        assertEq(nft.ownerOf(tokenId), bob);
        AIMarketCapabilityNFT.Entitlement memory e = nft.getEntitlement(tokenId);
        assertEq(e.transferCount, 1);
        assertEq(e.remainingCalls, 100); // unchanged
    }

    function test_transfer_revertsIfNotApproved() public {
        uint256 tokenId = nft.mint(alice, CAP_ID, PROD_ID, 100, 400_000);

        vm.prank(stranger);
        vm.expectRevert();
        nft.transferFrom(alice, bob, tokenId);
    }

    function test_transfer_viaApprove() public {
        uint256 tokenId = nft.mint(alice, CAP_ID, PROD_ID, 100, 400_000);

        vm.prank(alice);
        nft.approve(bob, tokenId);
        vm.prank(bob);
        nft.transferFrom(alice, bob, tokenId);
        assertEq(nft.ownerOf(tokenId), bob);
    }

    // ── ConsumeCall ──────────────────────────────────────────────

    function test_consumeCall_byAuthorizedHub() public {
        uint256 tokenId = nft.mint(alice, CAP_ID, PROD_ID, 3, 400_000);

        vm.prank(hub);
        uint64 remaining = nft.consumeCall(tokenId);
        assertEq(remaining, 2);

        vm.prank(hub);
        remaining = nft.consumeCall(tokenId);
        assertEq(remaining, 1);

        vm.prank(hub);
        remaining = nft.consumeCall(tokenId);
        assertEq(remaining, 0);
    }

    function test_consumeCall_revertsIfNotAuthorizedHub() public {
        uint256 tokenId = nft.mint(alice, CAP_ID, PROD_ID, 100, 400_000);

        vm.prank(stranger);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketCapabilityNFT.NotAuthorizedHub.selector, stranger)
        );
        nft.consumeCall(tokenId);
    }

    function test_consumeCall_revertsWhenExhausted() public {
        uint256 tokenId = nft.mint(alice, CAP_ID, PROD_ID, 1, 400_000);

        vm.prank(hub);
        nft.consumeCall(tokenId);

        vm.prank(hub);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketCapabilityNFT.NoCallsRemaining.selector, tokenId)
        );
        nft.consumeCall(tokenId);
    }

    function test_consumeCall_revertsForNonexistentToken() public {
        vm.prank(hub);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketCapabilityNFT.TokenDoesNotExist.selector, 999)
        );
        nft.consumeCall(999);
    }

    function test_consumeCall_worksAfterTransfer() public {
        uint256 tokenId = nft.mint(alice, CAP_ID, PROD_ID, 100, 400_000);
        vm.prank(alice);
        nft.transferFrom(alice, bob, tokenId);

        vm.prank(hub);
        uint64 remaining = nft.consumeCall(tokenId);
        assertEq(remaining, 99);
    }

    // ── Hub authorization ────────────────────────────────────────

    function test_setAuthorizedHub_revertsIfNotOwner() public {
        vm.prank(alice);
        vm.expectRevert();
        nft.setAuthorizedHub(alice, true);
    }

    function test_setAuthorizedHub_deauthorize() public {
        nft.setAuthorizedHub(hub, false);

        uint256 tokenId = nft.mint(alice, CAP_ID, PROD_ID, 100, 400_000);
        vm.prank(hub);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketCapabilityNFT.NotAuthorizedHub.selector, hub)
        );
        nft.consumeCall(tokenId);
    }

    // ── Burn ─────────────────────────────────────────────────────

    function test_burn_byOwner() public {
        uint256 tokenId = nft.mint(alice, CAP_ID, PROD_ID, 100, 400_000);
        vm.prank(alice);
        nft.burn(tokenId);

        vm.expectRevert();
        nft.ownerOf(tokenId);
    }

    function test_burn_revertsIfNotOwner() public {
        uint256 tokenId = nft.mint(alice, CAP_ID, PROD_ID, 100, 400_000);
        vm.prank(stranger);
        vm.expectRevert();
        nft.burn(tokenId);
    }

    // ── Views ────────────────────────────────────────────────────

    function test_remainingCalls_view() public {
        uint256 tokenId = nft.mint(alice, CAP_ID, PROD_ID, 50, 400_000);
        assertEq(nft.remainingCalls(tokenId), 50);

        vm.prank(hub);
        nft.consumeCall(tokenId);
        assertEq(nft.remainingCalls(tokenId), 49);
    }

    function test_isExhausted_view() public {
        uint256 tokenId = nft.mint(alice, CAP_ID, PROD_ID, 1, 400_000);
        assertFalse(nft.isExhausted(tokenId));

        vm.prank(hub);
        nft.consumeCall(tokenId);
        assertTrue(nft.isExhausted(tokenId));
    }

    function test_metadata_nameAndSymbol() public {
        assertEq(nft.name(), "AIMarket Capability Entitlement");
        assertEq(nft.symbol(), "AIMCAP");
    }

    // ── New: per-token consume pause ─────────────────────────────

    function test_setConsumePaused_byTokenOwner() public {
        uint256 tokenId = nft.mint(alice, CAP_ID, PROD_ID, 10, 400_000);

        vm.prank(alice);
        nft.setConsumePaused(tokenId, true);

        vm.prank(hub);
        vm.expectRevert(
            abi.encodeWithSelector(AIMarketCapabilityNFT.TokenConsumePaused.selector, tokenId)
        );
        nft.consumeCall(tokenId);

        // Owner can unpause
        vm.prank(alice);
        nft.setConsumePaused(tokenId, false);
        vm.prank(hub);
        nft.consumeCall(tokenId);
        assertEq(nft.remainingCalls(tokenId), 9);
    }

    function test_setConsumePaused_byContractOwner() public {
        uint256 tokenId = nft.mint(alice, CAP_ID, PROD_ID, 10, 400_000);

        // owner is `this`
        nft.setConsumePaused(tokenId, true);
        assertTrue(nft.consumePaused(tokenId));
    }

    function test_setConsumePaused_rejectsStranger() public {
        uint256 tokenId = nft.mint(alice, CAP_ID, PROD_ID, 10, 400_000);

        vm.prank(stranger);
        vm.expectRevert(
            abi.encodeWithSelector(
                AIMarketCapabilityNFT.NotTokenOwnerOrContractOwner.selector, stranger
            )
        );
        nft.setConsumePaused(tokenId, true);
    }

    // ── New: bulk-deauthorize ────────────────────────────────────

    function test_setAuthorizedHubBulk_deauthorize() public {
        address hub2 = address(0xBEEF1);
        address hub3 = address(0xBEEF2);
        nft.setAuthorizedHub(hub2, true);
        nft.setAuthorizedHub(hub3, true);

        address[] memory hubs = new address[](3);
        hubs[0] = hub;
        hubs[1] = hub2;
        hubs[2] = hub3;
        nft.setAuthorizedHubBulk(hubs, false);

        assertFalse(nft.authorizedHubs(hub));
        assertFalse(nft.authorizedHubs(hub2));
        assertFalse(nft.authorizedHubs(hub3));
    }

    function test_setAuthorizedHubBulk_revertsIfNotOwner() public {
        address[] memory hubs = new address[](1);
        hubs[0] = hub;
        vm.prank(stranger);
        vm.expectRevert();
        nft.setAuthorizedHubBulk(hubs, false);
    }

    // ── New: emergency pause ─────────────────────────────────────

    function test_pause_blocksMintAndConsume() public {
        uint256 tokenId = nft.mint(alice, CAP_ID, PROD_ID, 10, 400_000);

        nft.pause();

        vm.expectRevert(); // EnforcedPause
        nft.mint(alice, CAP_ID, PROD_ID, 10, 400_000);

        vm.prank(hub);
        vm.expectRevert();
        nft.consumeCall(tokenId);
    }

    function test_pause_allowsTransfers() public {
        // Pause shouldn't trap user funds — transfers must remain possible.
        uint256 tokenId = nft.mint(alice, CAP_ID, PROD_ID, 10, 400_000);
        nft.pause();

        vm.prank(alice);
        nft.transferFrom(alice, bob, tokenId);
        assertEq(nft.ownerOf(tokenId), bob);
    }

    function test_unpause_restoresConsume() public {
        uint256 tokenId = nft.mint(alice, CAP_ID, PROD_ID, 10, 400_000);
        nft.pause();
        nft.unpause();

        vm.prank(hub);
        nft.consumeCall(tokenId);
        assertEq(nft.remainingCalls(tokenId), 9);
    }

    // ── New: burn cleans up entitlement ──────────────────────────

    function test_burn_clearsEntitlement() public {
        uint256 tokenId = nft.mint(alice, CAP_ID, PROD_ID, 10, 400_000);
        vm.prank(alice);
        nft.burn(tokenId);

        // Stale view queries return safe values, not garbage from storage.
        assertEq(nft.remainingCalls(tokenId), 0);
        assertTrue(nft.isExhausted(tokenId));
        assertFalse(nft.consumePaused(tokenId));
    }
}
